# CareOps AI Web

This folder contains the web application for CareOps AI. The active frontend lives in `apps/web/careops-ui`.

Phase 6A in progress.

## What the frontend includes

- Public marketing homepage with a pipeline explainer, feature grid, and footer
- JWT auth flow: login and register with organization creation
- Dashboard: daily overview, KPIs, health score, live-intelligence card, revenue and margin trends
- Planning: the flagship trigger-and-watch experience, agent showcase, live scenario composition, SSE streaming pipeline, what-if simulator
- Action Center: pending approvals and full Action Queue history
- Analytics: historical drill-down across menu performance, channels, peak hours, and complaints
- Data: merged run history and data-health view, audit trail, PDF and Excel export
- AI Assistant chat: a conversational assistant over run history and guest feedback, streamed responses, plus a floating widget available on every page
- Market: live Swiggy market intelligence, one card per capability, with trend charts
- Workspace settings: capacity, cuisine, peak hours, planning thresholds
- Restaurant profiles: named profiles for per-run capacity and peak-hour overrides
- Multi-tenant isolation: all views scoped to the authenticated organization
- Guest Concierge (`/concierge`): a separate, no-auth consumer chat experience with venue, food, and event-supplies cards, voice input, and session history, sharing no data with the authenticated app above

## Start the app

```bash
cd careops-ui
npm install
npm run dev
```

Frontend at `http://localhost:3000`. Expects the API at `http://localhost:8000` by default.

## Environment

Set `NEXT_PUBLIC_API_BASE_URL` in `.env.local` if the backend runs elsewhere.

## More detail

See [`careops-ui/README.md`](careops-ui/README.md) for the full page-by-page breakdown.
