# CareOps AI UI

Next.js frontend for CareOps AI. Phase 6A in progress.

---

## Stack

- Next.js 16 (App Router)
- React 19
- TypeScript
- Tailwind CSS 4
- Recharts (charts)
- react-markdown (chat rendering)
- Fontsource: Instrument Serif, Plus Jakarta Sans, Space Mono
- Theming is hand-rolled (`context/ThemeContext.tsx`), not a third-party theme library. A small inline script in `app/layout.tsx` reads the saved theme from `localStorage` before hydration to avoid a flash, then toggles a `.dark` class on `<html>`.

---

## Pages

| Route | Auth | Purpose |
|-------|------|---------|
| `/` | Public | Marketing homepage |
| `/login` | Public | Sign in |
| `/register` | Public | Create a restaurant workspace |
| `/dashboard` | JWT | Daily overview: KPIs, health score, live-intelligence card, revenue and margin trends, top dishes, signals, upcoming risks, Action Queue summary, latest run. Triggering a scenario here navigates to `/planning` rather than running inline. |
| `/planning` | JWT | The flagship experience: agent showcase, live scenario composition, streaming pipeline run, forecast chart, critic banner, manager action panel, what-if simulator, run history, exports |
| `/action-center` | JWT | Pending approvals and full Action Queue history |
| `/analytics` | JWT | Historical drill-down: menu performance, channel split, peak hours, complaint categories, category pricing, a market-intelligence teaser |
| `/data` | JWT | Merged run history and data-health view, with PDF/Excel export and an observability summary |
| `/market` | JWT | Live Swiggy market intelligence, one card per capability, plus price and occupancy trend charts |
| `/chat` | JWT | Full-page AI Assistant, session list and suggested questions |
| `/connectors` | JWT | Swiggy connector status and sync trigger |
| `/restaurant-profiles` | JWT (owner) | Named restaurant profiles |
| `/settings` | JWT (owner) | Workspace configuration and planning thresholds |
| `/concierge` | Public, no auth | Guest Concierge: consumer chat for venue, food, and event-supplies planning via Swiggy |

`/operations`, `/runs`, `/runs/{id}`, and `/data-health` are thin client-side redirects to their current equivalents (`/planning` or `/data`), kept only so old bookmarks and links do not 404. None of them appear in navigation.

---

## Navigation

`components/layout/Sidebar.tsx` defines the primary navigation: Dashboard, Planning, Action Center, Analytics, and AI Assistant, plus a collapsible Admin section for Market, Data, Connectors, Restaurant Profiles (owner-only), and Settings (owner-only). `components/layout/TopBar.tsx` provides the theme toggle, restaurant/location selector, and user menu.

The public homepage uses its own `components/layout/HomeNav.tsx`, not the authenticated app's sidebar, and does not render for already-authenticated users, who are redirected to `/dashboard`.

---

## Dashboard

`components/dashboard/TodayIdleState.tsx` is the main component. It independently fetches data health, connector status, business performance and summary, the Action Queue, recent planning runs, and market pulse (weather, area demand, industry trends, FSSAI notices), and renders a KPI strip, a health-score gauge with an AI-generated executive summary, a live-intelligence card, revenue and margin trend charts, and four bottom cards for signals, upcoming risks, the Action Queue, and the latest run.

Triggering a scenario from the dashboard sets pending-trigger state and navigates to `/planning`, where the run actually executes.

---

## Planning

`app/planning/page.tsx` is the orchestrator for the flagship experience: it owns the SSE connection via the `useFridayRush` hook and composes the agent cards, forecast chart, critic banner, manager action panel, what-if panel, run history, observability strip, and evidence panel.

Its idle state, `components/planning/PlanningIdleState.tsx`, renders a compact trigger panel, a live-signals context card, a specialist showcase grid (`AgentPipelineGrid`), and a recent-runs strip. The "Run a plan" button opens `PlanShiftModal` (shared with the dashboard's quick-trigger flow), which offers running for today, choosing a preset scenario, or describing the shift in natural language. The "run for today" recommendation is produced by `hooks/useScenarioRecommendation.ts`, which composes a profile from live signals rather than forcing today into the nearest fixed preset, and is cached per hour so repeated page visits do not re-trigger the underlying LLM call on every mount.

---

## Action Center

`components/dashboard/ActionQueuePanel.tsx` renders pending approvals with the trust-ladder indicator; `components/data/ActionQueueHistory.tsx` renders the full history across all statuses.

---

## Analytics

`components/analytics/AnalyticsDetail.tsx` is a self-contained historical view: menu performance, channel split, peak hours, complaint categories, a category pricing chart, and a market-intelligence teaser linking to `/market`.

---

## Data

`components/data/RunHistorySection.tsx` (run list, run detail, PDF/Excel export, agent-by-agent breakdown) and `components/data/DataHealthSection.tsx` (data coverage and an observability summary) together make up this page, replacing the previous separate `/runs` and `/data-health` pages.

---

## Market

Renders `SwiggyStatusWidget`, `SwiggyLiveMarketPanel` (one card per Swiggy-backed capability: category pricing, positioning, menu breadth, cuisine crowding, veg mix, competitor deals, area occupancy, Dineout deals and slots, Instamart ingredient prices), and `MarketTrendChart` (per-dish price trend and occupancy trend across past runs).

---

## AI Assistant (Chat)

A conversational assistant over the organization's actual planning data, not generic AI. Available both as the full `/chat` page and as a floating widget (`components/chat/FloatingChatWidget.tsx`, mounted globally in `app/layout.tsx`), sharing session state through `context/ChatSessionContext.tsx` so switching between the two never loses context.

---

## Connectors, Restaurant Profiles, Settings

Each of these is a single, self-contained page component (`app/connectors/page.tsx`, `app/restaurant-profiles/page.tsx`, `app/settings/page.tsx`) rather than split into separate components. Connectors shows Swiggy connection status and a manual sync trigger. Restaurant Profiles is owner-gated CRUD for named profiles that override organization-level capacity and peak hours for a specific run. Settings is a field-config-driven form covering restaurant details and planning thresholds (critic approval score, low-stock and overstock warning percentages).

---

## Guest Concierge

`app/concierge/page.tsx` is a self-contained, no-auth chat experience, entirely separate from the authenticated app: its own sidebar (`components/concierge/ConciergeSidebar.tsx`), chat area (`ConciergeChatArea.tsx`), and result cards for venues, table slots, products, and order confirmations (`components/concierge/`). It does not render the authenticated app's `Sidebar`, `TopBar`, or `FloatingChatWidget`. Session identity and history live in `lib/conciergeHistory.ts` (browser-side) backed by the Redis-persisted session on the API; there is no organization or user account involved. Voice input is available via `ConciergeVoiceButton.tsx`, reusing the same recording flow as the operator chat and planning pages.

---

## Streaming

**Planning SSE** (`POST /api/v1/planning/stream`): `/planning` opens a `fetch` `ReadableStream` against this endpoint. Each node emits a `node_start` event, with a human-readable hint, when it begins, and a `node_complete` event when it finishes. The full plan arrives in a single `complete` event and renders all at once.

**Chat streaming** (`POST /api/v1/chat`): a separate mechanism. Tokens stream individually and render progressively through `react-markdown`.

---

## Local development

```bash
npm install
npm run dev
```

Frontend at `http://localhost:3000`.

```bash
# Point at a non-local backend
NEXT_PUBLIC_API_BASE_URL=http://your-backend-url
```

Set this in `.env.local` in this directory.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Backend API base URL |
