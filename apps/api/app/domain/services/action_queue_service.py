"""Approval-gated action infrastructure. Every agentic recommendation that isn't
purely informational -- a WhatsApp vendor order, a restock alert, a price change --
goes through this service rather than executing directly, so a human approves it
first (until the trust-ladder mechanic promotes that category to auto-execute).

This service only manages the approval lifecycle. It never executes anything
itself -- the caller of approve() is responsible for actually doing the thing
(e.g. sending the WhatsApp message), then calling mark_executed()/mark_error().
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.infrastructure.db.models import ActionQueue, ActionStatus, ActionTier


class ActionQueueService:
    def __init__(self, db: Session):
        self.db = db

    def create_action(
        self,
        org_id: int,
        category: str,
        title: str,
        payload: dict,
        tier: ActionTier = ActionTier.approve_required,
    ) -> ActionQueue:
        action = ActionQueue(
            org_id=org_id, category=category, title=title, payload=payload,
            tier=tier, status=ActionStatus.pending,
        )
        self.db.add(action)
        self.db.commit()
        self.db.refresh(action)
        return action

    def list_actions(self, org_id: int, status: ActionStatus | None = None) -> list[ActionQueue]:
        query = self.db.query(ActionQueue).filter(ActionQueue.org_id == org_id)
        if status is not None:
            query = query.filter(ActionQueue.status == status)
        return query.order_by(ActionQueue.created_at.desc()).all()

    def get(self, action_id: int) -> ActionQueue | None:
        return self.db.query(ActionQueue).filter(ActionQueue.id == action_id).first()

    def approve(self, action_id: int, user_id: int) -> ActionQueue:
        action = self._require(action_id)
        action.status = ActionStatus.approved
        action.approved_by = user_id
        self.db.commit()
        self.db.refresh(action)
        return action

    def reject(self, action_id: int, user_id: int) -> ActionQueue:
        action = self._require(action_id)
        action.status = ActionStatus.rejected
        action.approved_by = user_id
        self.db.commit()
        self.db.refresh(action)
        return action

    def mark_executed(self, action_id: int) -> ActionQueue:
        action = self._require(action_id)
        action.status = ActionStatus.executed
        action.executed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(action)
        return action

    def mark_error(self, action_id: int, error: str) -> ActionQueue:
        action = self._require(action_id)
        action.error = error[:500]
        self.db.commit()
        self.db.refresh(action)
        return action

    def update_payload(self, action_id: int, updates: dict) -> ActionQueue:
        """Merges `updates` into the action's payload -- e.g. an owner editing
        an LLM-drafted WhatsApp message before approving it. Reassigns the
        whole dict (not an in-place mutation) so SQLAlchemy's change tracking
        actually picks it up on the JSON column."""
        action = self._require(action_id)
        action.payload = {**action.payload, **updates}
        self.db.commit()
        self.db.refresh(action)
        return action

    def _require(self, action_id: int) -> ActionQueue:
        action = self.get(action_id)
        if action is None:
            raise ValueError(f"ActionQueue {action_id} not found")
        return action
