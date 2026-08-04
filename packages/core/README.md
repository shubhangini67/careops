# packages/core

Placeholder for shared contracts between the frontend and backend.

## Current status

No shared runtime code is checked in here yet, still true as of Phase 6A. Backend and frontend types live independently inside their respective app folders.

## Intended purpose

As the surface area between `apps/api` and `apps/web/careops-ui` grows, this package is the right place to consolidate:
- Shared API response types (TypeScript + Python Pydantic models)
- Scenario preset and profile definitions
- Critic dimension score schemas
- Planning run summary shapes
- Action Queue item shapes

## When to extract

Extracting shared types into this package is triggered when type drift between frontend and backend becomes a real maintenance problem, not on a fixed schedule.
