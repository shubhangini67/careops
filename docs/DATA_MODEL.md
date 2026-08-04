# CareOps AI Data Model

Reflects the implemented schema in `apps/api/app/infrastructure/db/models.py` and current Alembic migrations. Phase 6A in progress.

---

## Overview

CareOps AI uses three storage systems:

| Store | Role |
|-------|------|
| **PostgreSQL 16** | All structured operational data, auth, planning runs, settings |
| **Qdrant** | Five collections: RAG retrieval (`complaints_memory`, `sop_memory`), long-term planning memory (`planning_memory`), semantic plan cache (`semantic_cache`), chatbot Q&A cache (`chat_semantic_cache`): all org-scoped via payload filters |
| **Redis 7** | Plan cache: 1hr TTL by `(org_id, scenario, target_date)` |

---

## PostgreSQL Schema

### Enumerations

```python
class ReservationStatus(str, Enum):
    confirmed = "confirmed"
    cancelled = "cancelled"
    waitlist  = "waitlist"
    completed = "completed"

class SentimentType(str, Enum):
    positive = "positive"
    neutral  = "neutral"
    negative = "negative"

class FeedbackSource(str, Enum):
    google          = "google"
    in_person       = "in_person"
    zomato          = "zomato"
    swiggy          = "swiggy"
    swiggy_delivery = "swiggy_delivery"   # delivery tracking via track_food_order

class ConnectorType(str, Enum):
    swiggy         = "swiggy"
    pos_square     = "pos_square"
    google_reviews = "google_reviews"

class SyncStatus(str, Enum):
    never_synced = "never_synced"
    syncing      = "syncing"
    success      = "success"
    error        = "error"

class CriticVerdict(str, Enum):
    approved = "approved"
    rejected = "rejected"
    revision = "revision"

class UserRole(str, Enum):
    owner  = "owner"
    member = "member"

class ExpenseCategory(str, Enum):
    rent      = "rent"
    utilities = "utilities"
    marketing = "marketing"
    labor     = "labor"   # not populated yet -- no staffing feature exists; included so it
                          # slots in later without a schema change
    other     = "other"

class ExpenseRecurrence(str, Enum):
    one_time = "one_time"
    daily    = "daily"
    weekly   = "weekly"
    monthly  = "monthly"

class ActionTier(str, Enum):
    auto             = "auto"              # defined for a future auto-execution path; nothing
                                            # currently assigns this tier -- every action queue
                                            # item stays human-approved
    approve_required = "approve_required"  # default -- needs human approval before executing
    recommendation   = "recommendation"    # informational only, no execution path

class ActionStatus(str, Enum):
    pending  = "pending"
    approved = "approved"
    executed = "executed"
    rejected = "rejected"
    expired  = "expired"
```

---

### `organizations`

One row per restaurant workspace. All planning runs, settings, and profiles are scoped to an org.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `name` | String(100) | NOT NULL: display name |
| `slug` | String(100) | NOT NULL, unique: URL-safe identifier |
| `settings` | JSONB | Nullable: workspace config (capacity, timezone, peak hours, thresholds) |
| `created_at` | DateTime | UTC, set on insert |

**Default settings stored in JSONB:**
```json
{
  "capacity": 70,
  "timezone": "Asia/Kolkata",
  "cuisine_type": "pizza",
  "peak_hours": "18:00-22:00",
  "critic_threshold": 0.7,
  "low_stock_threshold_pct": 20.0,
  "overstock_threshold_pct": 150.0
}
```

**Relationships:** one org has many `UserOrganization`, `PlanningRun`, `RestaurantProfile`.

---

### `users`

One row per registered user.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `email` | String(255) | NOT NULL, unique |
| `hashed_password` | String(255) | NOT NULL: bcrypt hash |
| `full_name` | String(100) | Nullable: display name |
| `is_active` | Boolean | Default `true` |
| `created_at` | DateTime | UTC, set on insert |

**Relationships:** one user has many `UserOrganization` (a user can belong to multiple orgs, though the current registration flow creates one).

---

### `user_organizations`

Join table linking users to orgs with a role. Unique constraint on `(user_id, org_id)`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `user_id` | Integer FK → `users.id` | NOT NULL |
| `org_id` | Integer FK → `organizations.id` | NOT NULL |
| `role` | Enum(`UserRole`) | Default `member`: `owner` or `member` |
| `created_at` | DateTime | UTC, set on insert |

Registration creates a user + org + `user_organizations` row (role = `owner`) in one step.

---

### `restaurant_profiles`

Named restaurant profiles owned by an org. Overrides org-level capacity and peak hours for a specific planning run.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `org_id` | Integer FK → `organizations.id` | NOT NULL |
| `name` | String(100) | NOT NULL: e.g. `Casa Mia Rooftop` |
| `cuisine` | String(100) | Default `pizza` |
| `capacity` | Integer | Default `70`: seat count override |
| `peak_hours` | String(50) | Default `18:00-22:00` |
| `timezone` | String(50) | Default `Asia/Kolkata` |
| `created_at` | DateTime | UTC, set on insert |
| `updated_at` | DateTime | Auto-updated on write |

**Relationships:** belongs to `Organization`.

---

### `menu_items`

The restaurant's menu catalog.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `name` | String(100) | NOT NULL |
| `category` | String(50) | e.g. `pizza`, `beverage`, `dessert` |
| `price` | Float | NOT NULL |
| `is_available` | Boolean | Default `true` |
| `created_at` | DateTime | UTC, set on insert |

**Relationships:** one `MenuItem` has many `Order` records.

---

### `reservations`

Guest booking records.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `guest_name` | String(100) | NOT NULL |
| `guest_count` | Integer | NOT NULL |
| `reserved_at` | DateTime | NOT NULL: booking slot; used by Reservation node for peak-load analysis |
| `status` | Enum(`ReservationStatus`) | Default `confirmed` |
| `table_number` | Integer | Nullable |
| `notes` | Text | Nullable |
| `source` | String(50) | Default `internal`: values: `internal`, `dineout`, `eazydiner`, `phone` |
| `external_booking_id` | String(200) | Nullable: Dineout booking ID for dedup |
| `created_at` | DateTime | UTC, set on insert |

---

### `orders`

Individual order records. `ordered_at` is the primary signal for demand forecasting.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `menu_item_id` | Integer FK → `menu_items.id` | NOT NULL |
| `quantity` | Integer | NOT NULL |
| `total_price` | Float | NOT NULL |
| `ordered_at` | DateTime | Default UTC now: drives Prophet time-series forecasting |
| `is_delivery` | Boolean | Default `false` |
| `source` | String(50) | Default `internal`: values: `internal`, `swiggy`, `pos`, `zomato` |
| `channel` | String(50) | Default `dine_in`: values: `dine_in`, `delivery`, `takeaway` |
| `external_order_id` | String(200) | Nullable, unique: Swiggy order ID for dedup |

**Relationships:** belongs to `MenuItem`; one `Order` may have many `Feedback` records.

---

### `inventory`

Ingredient stock levels and shortage/overstock alerts.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `ingredient_name` | String(100) | NOT NULL |
| `unit` | String(20) | e.g. `kg`, `litres`, `units` |
| `quantity_in_stock` | Float | NOT NULL |
| `reorder_threshold` | Float | NOT NULL: shortage alert triggered when stock drops below this |
| `spoilage_risk` | Boolean | Default `false` |
| `updated_at` | DateTime | Auto-updated on write |

---

### `feedback`

Customer feedback and complaint text. Optionally linked to an order.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `order_id` | Integer FK → `orders.id` | Nullable |
| `raw_text` | Text | NOT NULL: complaint or review text |
| `sentiment` | Enum(`SentimentType`) | Nullable |
| `source` | Enum(`FeedbackSource`) | Default `in_person`: `swiggy_delivery` for delivery tracking rows |
| `delivery_time_actual_mins` | Integer | Nullable: from `track_food_order` |
| `delivery_time_promised_mins` | Integer | Nullable: ETA at order placement |
| `was_late` | Boolean | Nullable: `True` when actual > promised |
| `created_at` | DateTime | UTC, set on insert |

**Relationships:** optionally belongs to `Order`. Also used by the RAG chatbot: queried directly from Postgres by `ChatService`.

---

### `decision_logs`

Per-agent decision records for traceability.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `agent` | String(50) | NOT NULL: which node produced this |
| `input_summary` | Text | Nullable |
| `retrieved_context` | Text | Nullable: RAG context used |
| `reasoning_summary` | Text | Nullable |
| `action_recommended` | Text | NOT NULL |
| `critic_verdict` | Enum(`CriticVerdict`) | Nullable |
| `critic_score` | Float | Nullable: 0.0 to 1.0 |
| `critic_notes` | Text | Nullable |
| `metadata_` | JSONB | Nullable: stored as `metadata` in DB |
| `created_at` | DateTime | UTC, set on insert |

---

### `planning_runs`

Full output of each planning execution. Primary audit table; backs the `/data` page's run history section and the `/runs` and `/runs/{id}` redirect stubs.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `org_id` | Integer FK → `organizations.id` | Nullable: tenant scoping (Phase 5) |
| `scenario` | String(80) | NOT NULL: e.g. `friday_rush` |
| `target_date` | String(20) | Nullable: ISO date |
| `status` | String(40) | NOT NULL: `ready`, `needs_review`, or `blocked` |
| `critic_verdict` | String(40) | Nullable: `approved`, `revision`, or `rejected` |
| `critic_score` | Float | Nullable: 0.0 to 1.0 |
| `decision_log_id` | Integer | Nullable: link to `decision_logs` |
| `final_response` | JSONB | NOT NULL: full planning response payload |
| `recommendations` | JSONB | Nullable: per-agent blocks |
| `rag_context` | JSONB | Nullable: complaint and SOP context |
| `critic` | JSONB | Nullable: full critic output block |
| `metadata_` | JSONB | Nullable: stored as `metadata` in DB; includes `llm_usage`, `node_traces`, `cache_hit` |
| `generated_at` | DateTime | UTC, set on insert |
| `created_at` | DateTime | UTC, set on insert |

**Relationships:** belongs to `Organization`. All run queries filter by `org_id` for tenant isolation.

---

### `connectors`

Per-org external platform connector registry. Stores OAuth tokens (encrypted) and sync health per platform.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `org_id` | Integer FK → `organizations.id` | NOT NULL: tenant scoping |
| `connector_type` | String(50) | NOT NULL: `swiggy`, `pos_square`, `google_reviews` |
| `access_token_encrypted` | Text | Nullable: OAuth token (encrypted at rest) |
| `token_expires_at` | DateTime | Nullable: 5-day TTL for Swiggy tokens |
| `last_sync_at` | DateTime | Nullable: set on successful sync |
| `sync_status` | String(20) | Default `never_synced`: `never_synced`, `syncing`, `success`, `error` |
| `error_count` | Integer | Default 0: incremented on each sync failure |
| `last_error` | Text | Nullable: last error message |
| `created_at` | DateTime | UTC, set on insert |
| `updated_at` | DateTime | UTC, auto-updated on write |

**Unique constraint:** `(org_id, connector_type)`: one row per org per platform.

**Note:** `SWIGGY_ACCESS_TOKEN` in `.env` is a dev-only shortcut for single-org testing. Production reads the token from this table via `ConnectorRepository`.

---

### `expenses`

Per-org fixed or recurring cost (rent, utilities, marketing, other). Backs the financial scorecard's net-profit and health-score calculation.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `org_id` | Integer FK → `organizations.id` | NOT NULL |
| `category` | Enum(`ExpenseCategory`) | NOT NULL: `labor` exists in the enum but is not populated yet; no staffing feature exists |
| `amount` | Float | NOT NULL |
| `recurrence` | Enum(`ExpenseRecurrence`) | Default `one_time` |
| `effective_date` | DateTime | NOT NULL: when a one-time cost hit, or when a recurring cost started |
| `end_date` | DateTime | Nullable: null means still active, for recurring costs |
| `note` | String(200) | Nullable |
| `created_at` | DateTime | UTC, set on insert |

`BusinessAnalyticsService.get_daily_expense_total` prorates recurring costs into a daily-equivalent figure (for example, Rs 50,000 a month in rent becomes roughly Rs 1,667 a day).

---

### `action_queue`

A proposed action awaiting approval (for example, "reorder mozzarella from Ramesh Traders via WhatsApp"). Every item stays at the `approve_required` or `recommendation` tier in practice: nothing currently promotes a category to `auto`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `org_id` | Integer FK → `organizations.id` | NOT NULL |
| `category` | String(50) | NOT NULL: the specific kind of action (e.g. `whatsapp_vendor_order`, `restock_alert`); the trust ladder counts consecutive approvals against this, not `tier` |
| `tier` | Enum(`ActionTier`) | Default `approve_required`; nothing currently promotes a category to `auto` |
| `status` | Enum(`ActionStatus`) | Default `pending` |
| `title` | String(200) | NOT NULL |
| `payload` | JSON | NOT NULL: whatever the executing code needs to actually carry out the action |
| `approved_by` | Integer FK → `users.id` | Nullable |
| `executed_at` | DateTime | Nullable |
| `error` | String(500) | Nullable |
| `created_at` | DateTime | UTC, set on insert |

This table manages the approval lifecycle only; it does not execute anything itself.

---

### `vendors`

A procurement source: a local vendor reached by WhatsApp or phone, or an online source like Instamart.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `org_id` | Integer FK → `organizations.id` | NOT NULL |
| `name` | String(100) | NOT NULL |
| `category` | String(50) | Nullable: e.g. `dairy`, `produce`, `general` |
| `is_online` | Boolean | Default `false`: real procurement today is manual (phone, market visits, WhatsApp), so `false` is the common case |
| `whatsapp_number` | String(20) | Nullable: E.164 format |
| `created_at` | DateTime | UTC, set on insert |

**Relationships:** one `Vendor` has many `VendorPriceQuote`.

---

### `vendor_price_quotes`

A vendor's quoted price for one ingredient at a point in time, letting a cheapest-vendor-per-ingredient comparison be computed without a live API call for every source.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `vendor_id` | Integer FK → `vendors.id` | NOT NULL |
| `ingredient` | String(100) | NOT NULL |
| `price` | Float | NOT NULL |
| `quoted_at` | DateTime | UTC, set on insert |

---

### `chat_sessions` and `chat_messages`

A single chat conversation thread and its messages.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `org_id` | Integer FK → `organizations.id` | NOT NULL (session only) |
| `user_id` | Integer FK → `users.id` | NOT NULL (session only) |
| `title` | String(200) | Nullable: a cheap truncated preview of the first user message; no LLM call needed to label a thread |
| `session_id` | Integer FK → `chat_sessions.id` | NOT NULL (message only) |
| `role` | String(20) | NOT NULL (message only): `user` or `assistant` |
| `content` | Text | NOT NULL (message only) |
| `created_at` / `updated_at` | DateTime | UTC |

**Relationships:** one `ChatSession` has many `ChatMessage`, cascade-deleted with the session.

---

## Entity Relationships

```
Organization ──< UserOrganization >── User
Organization ──< RestaurantProfile
Organization ──< PlanningRun
Organization ──< Connector
Organization ──< Expense
Organization ──< ActionQueue
Organization ──< Vendor >──< VendorPriceQuote
Organization ──< ChatSession >──< ChatMessage

MenuItem ──< Order >──< Feedback

Reservation   (standalone: no FK to other operational tables)
Inventory     (standalone: per-ingredient stock record)
DecisionLog   (standalone: optionally linked from PlanningRun)
```

---

## Qdrant Collections

### `complaints_memory`

Stores embedded complaint and review text for RAG retrieval. Org-scoped via `org_id` payload filter.

**Payload fields per point:**

| Field | Description |
|-------|-------------|
| `text` | Raw complaint or review text |
| `org_id` | Tenant isolation: all retrieval calls filter by this |
| `complaint_type` | e.g. `slow_service`, `cold_food`, `wrong_order` |
| `sentiment` | `positive`, `neutral`, or `negative` |
| `source` | Platform of origin |
| `date` | When the complaint was recorded |
| `tags` | List of operational tags |

**Used by:** Complaint Intelligence node (planning pipeline) and ChatService (RAG chatbot).

---

### `sop_memory`

Stores embedded standard operating procedures and operational guidance.

**Payload fields per point:**

| Field | Description |
|-------|-------------|
| `text` | SOP or guideline content |
| `org_id` | Tenant isolation |
| `category` | Operational area: e.g. `kitchen`, `service`, `inventory` |
| `title` | Short descriptive title |
| `applicable_area` | Where this SOP applies |
| `tags` | List of tags for filtering |

**Used by:** Complaint Intelligence node to pair complaint patterns with relevant SOPs as evidence-backed action guidance.

---

### `planning_memory`

Stores embedded approved-run insights for long-term planning memory. Retrieved at planning time by the `qdrant_enrichment` node to enrich the current run with similar historical context.

**Written to:** After every approved planning run (verdict == "approved"). Not written for revision or rejected runs.

**Retrieval:** ANN search + recency decay re-ranking (`score × 2^(-age/RECENCY_HALF_LIFE_DAYS)`). Runs older than 90 days excluded. Over-fetches 2×top_k then re-ranks.

**Payload fields per point:**

| Field | Description |
|-------|-------------|
| `org_id` | Tenant isolation: all retrieval calls filter by this |
| `scenario` | Planning scenario id (e.g. `friday_rush`) |
| `run_id` | Planning run ID for traceability |
| `timestamp` | ISO timestamp: used for recency decay scoring |
| `insight_text` | Embedded insight: `"scenario:X | demand_ratio:1.4 | shortages:chicken,basil | occupancy:72% | verdict:approved score:0.82 | menu:..."` |

**Constants:** `RECENCY_HALF_LIFE_DAYS=14`, `MAX_MEMORY_AGE_DAYS=90`

**Used by:** `qdrant_enrichment` node via `PlanningMemoryService`.

---

### `semantic_cache`

Qdrant-backed semantic plan cache. Distinct from the Redis key-value plan cache: uses embedding similarity so semantically similar scenarios on similar dates return a cached result even if the exact (org, scenario, date) key doesn't match.

**Written to:** After every approved planning run. Rejected and revision runs are never cached.

**Hit threshold:** Cosine similarity ≥ 0.92  
**TTL:** 1 hour (checked via `cached_at` payload field)

**Two-embedding strategy:**
- **Storage embedding** (`_storage_text()`): enriched: includes `demand_ratio`, `occupancy%`, `shortages`, `verdict` for higher future matching precision
- **Query embedding** (`_query_text()`): lightweight: `"org:{id} scenario:{scenario} date:{date}"` (conditions not known at query time)

**Payload fields per point:**

| Field | Description |
|-------|-------------|
| `org_id` | Tenant isolation |
| `scenario` | Planning scenario id |
| `target_date` | ISO date or `"next"` |
| `cached_at` | ISO timestamp for TTL check |
| `result` | JSON-serialised full planning response |

**Used by:** `SemanticPlanCache` in `infrastructure/cache/semantic_cache.py`.

---

### `chat_semantic_cache`

Embedding-based cache for chatbot Q&A pairs. Returns cached answers for near-identical questions without an LLM call.

**Hit threshold:** Cosine similarity ≥ 0.92  
**TTL:** 24 hours

**Payload fields per point:**

| Field | Description |
|-------|-------------|
| `org_id` | Tenant isolation |
| `question` | First 500 chars of the question text |
| `answer` | Cached answer string |
| `cached_at` | ISO timestamp for TTL check |

**Used by:** `SemanticChatCache` in `infrastructure/cache/semantic_cache.py`.

---

## Redis

Redis 7 is used for two purposes:

### Plan cache (key-value)
**Cache key:** `plan:{org_id}:{scenario}:{target_date}`  
**TTL:** 1 hour  
**On hit:** full planning response returned immediately; `cache_hit: true` in response  
**On miss:** pipeline executes; result stored after completion  
**Invalidation:** automatic TTL expiry only

### Circuit breaker state
Redis keys per Swiggy MCP endpoint (`food`, `im`, `dineout`):
- `circuit:fail:swiggy:{tag}`: failure counter; INCR with 300s TTL auto-expiry
- `circuit:open:swiggy:{tag}`: open flag; SETEX with a 10-minute TTL

Failure counter reaching 5 within the 5-minute window sets the open flag. Open flag auto-expires (no explicit reset needed). `record_success()` DELs the failure counter for faster recovery. `is_open()` fails open (returns False) if Redis is unavailable.

Connection default: `redis://localhost:6379/0`

### Guest Concierge sessions

Guest Concierge deliberately has no footprint anywhere else in this schema: no `org_id`, no user account, no PostgreSQL row, no Qdrant point. Each session (`ConciergeSession`) is a single Redis key (`concierge_session:{session_id}`) holding occasion, headcount, budget, preferences, active bookings and orders, and the Instamart cart as JSON, with a 2-hour TTL.

---

## Seed Data

Demo data is populated by scripts in `scripts/`:

- `seed_demo_data.py`: generates ~6500 orders, ~1200 reservations, ~160 feedback records, 18 inventory items, and 27 menu items into PostgreSQL
- `seed_qdrant_memory.py`: embeds and loads complaint patterns and SOPs into Qdrant

Run after `alembic upgrade head`. See the root README for the full setup sequence.
