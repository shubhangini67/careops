"""Trust-ladder -- tracks how many times in a row a category of action has been
approved, purely as an informational signal. Deliberately does NOT auto-promote
a category to skip approval: the 2026-07-08 restaurant-owner call confirmed the
manager wants to stay in the loop on every vendor communication and pricing
decision, so letting the system bypass review after N approvals would contradict
the exact reality this whole Action Queue is built around. This is a visible
"you've approved this kind of thing N times in a row" badge, nothing more.
"""

from sqlalchemy.orm import Session

from app.infrastructure.db.models import ActionQueue, ActionStatus


class TrustLadderService:
    def __init__(self, db: Session):
        self.db = db

    def count_consecutive_approvals(self, org_id: int, category: str) -> int:
        """Counts backward from the most recent decided action of this org+category:
        each approved/executed action extends the streak, the first rejected one
        ends it. Pending/expired actions aren't 'decided' yet so they're excluded
        from the ordering rather than breaking or extending the streak."""
        decided = (
            self.db.query(ActionQueue)
            .filter(
                ActionQueue.org_id == org_id,
                ActionQueue.category == category,
                ActionQueue.status.in_([ActionStatus.approved, ActionStatus.executed, ActionStatus.rejected]),
            )
            .order_by(ActionQueue.created_at.desc())
            .all()
        )
        streak = 0
        for action in decided:
            if action.status == ActionStatus.rejected:
                break
            streak += 1
        return streak
