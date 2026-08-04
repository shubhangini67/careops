"""action_queue.py — approve/reject agentic recommendations.

GET /api/v1/action-queue lists pending/approved/rejected/executed actions for
the org. POST .../reject just transitions status. POST .../approve transitions
status AND, for whatsapp_vendor_order actions, triggers the actual WhatsApp
send (P6-A9) -- approval and execution are the same step for that action kind,
since there's nothing further to approve once a human has reviewed the drafted
message. Other action categories may not have an execution step wired yet.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db, get_llm
from app.domain.services.action_execution_service import approve_and_execute
from app.domain.services.action_queue_service import ActionQueueService
from app.domain.services.trust_ladder_service import TrustLadderService
from app.domain.services.workflow_trigger_service import WorkflowTriggerService
from app.infrastructure.db.models import ActionStatus
from app.infrastructure.llm.base import BaseLLMProvider

router = APIRouter(prefix="/action-queue", tags=["action-queue"])


class ActionQueueItem(BaseModel):
    id: int
    category: str
    tier: str
    status: str
    title: str
    payload: dict
    approved_by: int | None = None
    executed_at: str | None = None
    error: str | None = None
    created_at: str | None = None
    approval_streak: int = 0


def _to_item(a, approval_streak: int = 0) -> ActionQueueItem:
    return ActionQueueItem(
        id=a.id, category=a.category, tier=a.tier.value, status=a.status.value,
        title=a.title, payload=a.payload, approved_by=a.approved_by,
        executed_at=a.executed_at.isoformat() if a.executed_at else None,
        error=a.error,
        created_at=a.created_at.isoformat() if a.created_at else None,
        approval_streak=approval_streak,
    )


@router.get("", response_model=list[ActionQueueItem])
def list_actions(
    status_filter: ActionStatus | None = Query(default=None, alias="status"),
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ActionQueueItem]:
    service = ActionQueueService(db)
    trust_ladder = TrustLadderService(db)
    actions = service.list_actions(current["org_id"], status=status_filter)
    return [
        _to_item(a, approval_streak=trust_ladder.count_consecutive_approvals(current["org_id"], a.category))
        for a in actions
    ]


class ApproveActionRequest(BaseModel):
    # Lets the owner edit a drafted (LLM or template) WhatsApp message before
    # it actually sends -- a draft is a starting point, not something that
    # goes out verbatim without a last human look. Ignored for any other
    # action category.
    message_override: str | None = None


@router.post("/{action_id}/approve", response_model=ActionQueueItem)
def approve_action(
    action_id: int,
    body: ApproveActionRequest = ApproveActionRequest(),
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionQueueItem:
    service = ActionQueueService(db)
    existing = service.get(action_id)
    if existing is None or existing.org_id != current["org_id"]:
        raise HTTPException(status_code=404, detail="Action not found.")
    action = approve_and_execute(db, action_id, current["user_id"], body.message_override)
    return _to_item(action)


@router.post("/{action_id}/reject", response_model=ActionQueueItem)
def reject_action(
    action_id: int,
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionQueueItem:
    service = ActionQueueService(db)
    action = service.get(action_id)
    if action is None or action.org_id != current["org_id"]:
        raise HTTPException(status_code=404, detail="Action not found.")
    action = service.reject(action_id, current["user_id"])
    return _to_item(action)


class VendorMessageRequest(BaseModel):
    vendor_id: int
    ingredient: str
    unit: str | None = None
    quantity_in_stock: float | None = None
    reorder_threshold: float | None = None
    recommended_restock_qty: float | None = None
    reason: str | None = None


@router.post("/vendor-message", response_model=ActionQueueItem)
async def create_vendor_message(
    body: VendorMessageRequest,
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    llm: BaseLLMProvider = Depends(get_llm),
) -> ActionQueueItem:
    """Owner picked a specific vendor from the "Message Your Vendors" list --
    drafts a real WhatsApp order for it (same pending, approve-to-send flow
    as any other whatsapp_vendor_order action)."""
    service = WorkflowTriggerService(db, llm)
    try:
        action = await service.create_vendor_message(
            current["org_id"], body.vendor_id,
            {
                "ingredient": body.ingredient,
                "unit": body.unit,
                "quantity_in_stock": body.quantity_in_stock,
                "reorder_threshold": body.reorder_threshold,
                "recommended_restock_qty": body.recommended_restock_qty,
            },
            body.reason,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    return _to_item(action)
