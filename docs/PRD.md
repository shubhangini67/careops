# Product Requirements Document (PRD)
# CareOps AI

Phase 6A in progress, including Guest Concierge.

---

## 1. Project Overview

CareOps AI is a two-sided platform powered by the Swiggy MCP. Side one, Restaurant OS, is the original focus: specialist agents read demand data, bookings, guest complaints, menu performance, inventory, and live external signals in parallel and produce a single critic-verified pre-shift brief before every shift. Side two, Guest Concierge, is a consumer-facing event-planning assistant: a no-auth `/concierge` experience where a guest describes an occasion and the system plans it end-to-end (venue, food, supplies) directly through Swiggy's Food, Instamart, and Dineout MCP servers, independently of any specific restaurant's data. Guest Concierge is delivered, not gated on separate Swiggy consent: it is the Proposed Arrangement described in clause 1.1 of the signed Integration Agreement.

It is not a chatbot and not a basic RAG demo. It is a multi-agent AI system combining time-series forecasting, vector retrieval, LLM reasoning, streaming delivery, and business-rule validation to support restaurant operations, plus a second, independent agentic assistant for consumers.

A critic agent reviews the restaurant-side plan across five quality dimensions before it reaches the manager. If anything looks unsafe or unrealistic, the plan is blocked and the reason is explained.

---

## 2. Problem Statement

Restaurants often struggle with:
- Unpredictable rush hours with no data-driven demand signal
- Inefficient reservation handling and occupancy blind spots
- Recurring guest complaints that never make it into the pre-shift brief
- Weak visibility into menu performance and what to push tonight
- Inventory shortages discovered mid-service instead of before the shift
- No single verified plan: just four dashboards, a spreadsheet, and a group chat

CareOps AI fills that gap with a structured multi-agent system that reasons over restaurant data and produces explainable, governed recommendations: before every shift, in under 90 seconds.

Guests planning an event (a birthday, an anniversary dinner, a team lunch) face a parallel but separate problem: finding a venue, checking real availability, ordering food, and sourcing supplies means juggling several apps with no single assistant that plans the whole thing together.

---

## 3. Vision

A multi-agent AI operating layer for restaurant operations that is:
- Intelligent: combines forecasting, retrieval, and LLM reasoning
- Explainable: every recommendation is backed by data and a critic verdict
- Streaming: results arrive node by node, not as a single slow response
- Production-minded: Redis caching, OTel tracing, Sentry, LangSmith evals
- Multi-tenant: one platform, isolated per restaurant org
- Integrated: connects to live platforms (Swiggy) for real demand, market, and procurement data
- Governed: circuit breaker, provider registry, and tool tracing protect all external API calls

Alongside a Guest Concierge that is:
- Independent: no restaurant-operator data, no shared session state, no auth required
- Honest: never claims a booking or order succeeded when it didn't; staging-gated actions are shown as pending, not hidden or faked
- Agentic: a real ReAct tool-calling loop over 20 Swiggy tools across Food, Instamart, and Dineout, not a scripted flow

---

## 4. Goals

### Primary
- Multi-agent planning pipeline (LangGraph, fifteen nodes) across preset and free-form shift scenarios
- Demand forecasting with Prophet time-series, adjusted by real weather and holiday signals
- RAG complaint intelligence over Qdrant
- 5-dimension critic quality gate (safety, feasibility, evidence, actionability, clarity)
- SSE streaming with live pipeline diagram
- PDF and Excel exports (chef view and owner view)
- Chat assistant over run history, feedback, and Swiggy market and Action Queue tools
- A no-auth Guest Concierge that plans a consumer's event end-to-end via Swiggy

### Phase 6A: delivered
- Swiggy MCP integration: area-level market signals, occupancy, Instamart procurement enrichment
- Compliance remediation: removal of a competing-platform stub connector, anonymisation of market intelligence to area aggregates
- Long-term planning memory (PlanningMemoryService) with recency decay
- Semantic plan cache (Qdrant-backed, approved-only, condition-enriched embeddings)
- MCP governance: circuit breaker, provider registry, tool tracing
- Live intelligence signals independent of Swiggy: weather and holidays, industry trends, regulatory alerts, unified into the planning pipeline
- Natural-language and dynamically composed scenario intake, alongside the four presets
- Action Queue with an informational trust-ladder badge (consecutive-approval streak, not an auto-execution mechanic) and a financial scorecard (real net profit, net margin, composite health score)
- Langfuse tracing on every planning run, with a Kindred replay endpoint for prompt-level debugging
- Frontend information architecture redesign: separate Dashboard and Planning pages, a merged Data page, a dedicated Action Center and Analytics page
- Homepage redesigned around the two-sided platform (dual entry: restaurant sign-in, guest sign-in), `/login`/`/register` redesigned on a shared split-screen layout
- Market Intelligence page: every signal card (weather, trends, regulatory alerts) always renders, showing an honest "unavailable" state instead of disappearing when a signal is missing
- **Guest Concierge**: no-auth `/concierge` page and `ConciergeService`, a ReAct tool-calling loop over 20 Swiggy Food/Instamart/Dineout tools, real venue/slot/product/order cards, session history, voice input, staging-gated booking and checkout shown honestly as pending

### Phase 6A: upcoming
- Autonomous procurement loop wired fully end-to-end (shortage detection through real Instamart checkout), currently blocked on Swiggy staging credentials for the checkout step
- Guest Concierge table booking and Instamart checkout execution, blocked on the same staging credentials
- Voice output (TTS) for both the operator chat and Guest Concierge; voice input (Whisper transcription) is already live on both
- Promotion of RAGAS and DeepEval candidate datasets into the golden eval fixtures

### Secondary
- LangSmith golden dataset + 90% CI quality gate
- OpenTelemetry, Prometheus, Sentry observability
- Redis plan caching (1hr TTL, zero LLM cost on hits)
- Multi-tenant workspace isolation (Postgres + Qdrant)
- What-if simulator for instant cover count adjustment
- MCP server for Claude Code / Claude Desktop integration

---

## 5. Non-Goals (current phase)

- Live POS integrations
- Production cloud deployment
- Payment processing
- Mobile app
- Full staff scheduling engine
- Real Instamart checkout and Dineout table booking (both restaurant-side procurement and Guest Concierge): implemented in code but blocked on Swiggy staging credentials, not yet exercised against a live account

---

## 6. Target Users

### Primary
- Restaurant manager / ops lead planning a shift for a casual dining restaurant
- A guest planning a dining occasion (birthday, anniversary, team lunch, date night) who wants one assistant to handle venue, food, and supplies

### Secondary
- Restaurant owners reviewing cost and quality trends
- Founders evaluating vertical AI SaaS ideas
- Engineers and recruiters reviewing system design maturity

---

## 7. Core Use Cases

### Restaurant OS
1. Select a preset scenario (Friday Rush, Weekday Lunch, Holiday Spike, Low-Stock Weekend), describe one in free text, or let the system compose one from current live signals
2. Run the planning pipeline on the `/planning` page: watch agents complete in real time via SSE
3. Review the critic-verified plan (demand, reservations, complaints, menu, inventory, live market signals)
4. Export a PDF chef brief or Excel owner workbook
5. Adjust cover count in the what-if simulator without a full re-run
6. Ask the chat assistant questions about past runs, complaints, performance, live market data, and pending actions, by voice or text
7. Review and approve pending Action Queue items on the Action Center page
8. Review run history with critic score trends and full detail, and monitor data coverage, on the merged Data page
9. Review daily KPIs, health score, and live-intelligence context on the Dashboard page
10. Drill into historical menu, channel, peak-hour, and complaint performance on the Analytics page

### Guest Concierge
1. Land on the homepage, choose "Sign in as Guest" (no account needed), and land on `/concierge`
2. Describe an occasion in one message (occasion, headcount, budget, locality, preferences), by voice or text
3. Review real Dineout venues with estimated cost and deals, check real table-slot availability, and request a booking
4. Browse a real restaurant menu and build a food delivery order, capped at Rs.1000 per order (Builders Club v1, COD only)
5. Get proactive Instamart supply suggestions (cake, decorations, drinks) for the occasion, and build a supplies cart
6. Track budget spent vs. remaining, active bookings, and active orders in a persistent sidebar
7. Resume a previous plan from a local, no-account history list, or start a new one

---

## 8. Delivered Features

### Planning pipeline
- Fifteen-node LangGraph StateGraph with parallel fan-out across five domain agents (reservation, complaint intelligence, inventory, market intelligence, Dineout management); menu intelligence runs sequentially after with access to all five outputs
- Four scenario presets (`friday_rush`, `weekday_lunch`, `holiday_spike`, `low_stock_weekend`), plus free-text natural-language scenario intake and dynamic composition from current live signals
- Prophet time-series demand forecasting, adjusted by a real weather and holiday multiplier, with peak detection
- Qdrant RAG complaint intelligence, org-scoped payload filter
- Menu performance analysis: push, ease-back, or avoid strategy
- Inventory shortage and overstock detection with restock priority
- Live intelligence signals (weather and holidays, industry trends, FSSAI regulatory alerts) merged with anonymised Swiggy area signals into one market intelligence output
- 5-dimension critic scoring: safety, feasibility, evidence, actionability, clarity
- Verdicts: approved / revision / rejected

### Streaming & UX
- FastAPI SSE streaming (`/planning/stream`): `node_complete` status events update the loading screen pipeline diagram as each node finishes; full plan delivered in a single `complete` event
- Branded loading screen with restaurant name and live pipeline diagram
- Redis 1hr plan cache: `cache_hit` flag in response, zero LLM cost on hits
- What-if simulator: cover count slider, instant cost/benefit/tradeoff update
- Market Intelligence signal cards (weather, trends, regulatory alerts) always render, with an honest "unavailable" state rather than vanishing when a signal fails or is missing

### Exports
- PDF chef brief: ReportLab, plan summary + action items + dimension scores
- Excel workbook: openpyxl, Inventory & Staffing sheet + Cost Breakdown sheet

### Action Queue and financial scorecard
- Action Queue with approve/reject flows and an informational trust-ladder badge (a "you've approved this category N times in a row" streak counter); it does not auto-promote any category to skip approval, by deliberate design: every action stays human-approved
- Vendor and vendor-price-quote records backing WhatsApp-based procurement coordination
- Real net profit, net margin, and a composite health score, backed by a per-org expense ledger with cost proration

### Operator chat assistant
- Chat over Postgres `planning_runs` and `feedback` tables (org-scoped), plus function-calling tools for Swiggy market data and Action Queue actions
- SSE token streaming, ReactMarkdown rendering, full page and floating widget on every page
- Voice input (Whisper transcription via Groq) on the full chat page and the floating widget
- Multi-turn conversation with session summarisation for long threads, suggested starter questions

### Guest Concierge
- `ConciergeService`: a ReAct tool-calling loop (Groq function calling) over 20 tools across Swiggy Food, Instamart, and Dineout MCP servers, with Redis-backed session state (2-hour TTL) and no restaurant-operator data
- No-auth `/concierge` API routes (chat, session, transcribe, health) and a consumer-facing `/concierge` frontend page with no operator chrome, even if an operator happens to be logged in in the same browser
- Real venue, slot, product, and order cards rendered from structured tool results, not narrated as prose
- Proactive Instamart supply suggestions for birthday/party occasions
- Voice input, light/dark theme toggle, a local (no-account) previous-plans history, and a logout affordance for an operator previewing the flow
- Staging-gated actions (table booking, Instamart checkout) shown honestly as "pending", never hidden or faked; every guest-facing failure degrades to a friendly message, never a raw exception or internal tool name

### Observability & quality
- OpenTelemetry HTTP tracing on every route
- Prometheus `/metrics` scrape endpoint
- Sentry unhandled exception capture with LangGraph node tags
- LangSmith per-node traces + `careops-golden-v1` dataset (50 runs)
- CI quality gate: 90% pass rate on golden dataset
- RAGAS faithfulness ≥ 0.8 on complaint RAG pipeline
- DeepEval hallucination ≤ 0.5, relevancy ≥ 0.7 on critic and agent outputs

### Multi-tenant isolation
- JWT org-scoped sessions; all run queries filter by `org_id`
- Qdrant payload filter per org on complaint and SOP vectors
- `org_id` in `OrchestratorState` for end-to-end isolation
- Guest Concierge sessions are deliberately outside this model: no `org_id`, no user account, disposable Redis state only

### Auth & config
- JWT (HS256) register + login with org creation, restaurant-operator side only
- Workspace settings: capacity, cuisine, peak hours, thresholds
- Restaurant profiles: named overrides per planning run (owner only)
- Homepage and `/login`/`/register` redesigned around the two-sided platform, with a dual entry point and a shared split-screen auth layout

### MCP integration
- Five tools via the Anthropic MCP SDK: `run_planning_scenario`, `get_run_history`, `get_market_brief`, `get_action_queue`, `approve_action`
- Auto-discovered by Claude Code via `.mcp.json`; Claude Desktop uses `docs/mcp_claude_desktop_config.json`

---

## 9. Non-Functional Requirements

- Modular architecture: route / orchestration / service / infrastructure layers clearly separated
- Local reproducibility with Docker Compose (PostgreSQL, Qdrant, Redis)
- Swappable LLM provider: Groq default, Gemini fallback, config-only switch
- Testable at every layer: unit, integration, LLM quality evals
- Explainable outputs: every recommendation backed by data + critic verdict
- Documentation-first: every capability documented against the actual current implementation, not aspirational scope
- Guest-facing surfaces never leak raw exceptions, internal tool names, or third-party API error payloads; every failure degrades to a fixed, friendly message

---

## 10. Success Criteria

The project is successful if:
- All four presets, plus free-text and dynamically composed scenarios, run end-to-end with critic-verified output
- SSE streaming works: users see results arrive node by node
- PDF and Excel exports are usable by a real chef or owner
- The chat assistant answers questions using the org's actual data and can act on pending Action Queue items
- LangSmith CI gate passes: 90% of golden dataset runs meet the evaluator thresholds (critic score ≥ 0.70)
- Every Swiggy integration is compliant with the signed Integration Agreement and clearly attributed with Swiggy branding
- A guest can describe an occasion in one message and get real venues, real availability, and real supply suggestions back, with no account and no restaurant-operator data involved
- The system is presentable as a production-grade AI platform in interviews and demos

---

## 11. Constraints

- Solo developer project
- Local-first setup (Docker Compose)
- Free-tier LLM providers (Groq, Gemini), with CometAPI available for tiered model routing
- Operational data (orders, reservations, feedback) is synthetic seed data; Swiggy market signals, weather, industry trends, and regulatory alerts are real live data; Guest Concierge's Swiggy calls are real, live requests against a Builders Club v1 test account
- A signed Swiggy Integration Agreement is in effect: exclusivity and competitive-intelligence clauses constrain what the Swiggy integration may do, and clause 1.1 is what makes Guest Concierge compliant as written rather than requiring separate consent (see `CLAUDE.md` and `docs/DECISIONS.md`)
- Architecture should look enterprise-grade regardless
