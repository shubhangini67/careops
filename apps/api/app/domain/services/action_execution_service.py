"""Shared 'approve and execute' orchestration for actions whose approval and
execution are the same step (e.g. a WhatsApp vendor order -- there's nothing
further to approve once a human has reviewed the drafted message).

Used identically by the HTTP API route (app/api/routes/action_queue.py), the
in-app chatbot's approve_action tool, and the MCP server's approve_action tool
(via HTTP), so approving an action goes through the same logic regardless of
which surface the human used to say "approve this."
"""

from sqlalchemy.orm import Session

from app.domain.services.action_queue_service import ActionQueueService
from app.domain.services.vendor_service import VendorService
from app.infrastructure.db.models import ActionQueue
from app.infrastructure.whatsapp.whatsapp_service import WhatsAppSendError, WhatsAppService


def approve_and_execute(
    db: Session, action_id: int, user_id: int, message_override: str | None = None,
) -> ActionQueue | None:
    """Approves an action and, for whatsapp_vendor_order, triggers the real
    Twilio send immediately after. Returns the updated action, or None if it
    doesn't exist -- callers are responsible for org-ownership checks before
    calling this.

    message_override lets the owner edit a drafted (LLM or template) message
    before it actually sends -- a draft is a starting point, never something
    that goes out verbatim without the human's last look."""
    service = ActionQueueService(db)
    action = service.get(action_id)
    if action is None:
        return None

    if message_override is not None and action.category == "whatsapp_vendor_order":
        action = service.update_payload(action_id, {"message_draft": message_override})

    action = service.approve(action_id, user_id)

    if action.category == "whatsapp_vendor_order":
        action = _send_whatsapp_order(service, VendorService(db), action)

    return action


def _send_whatsapp_order(
    service: ActionQueueService, vendor_service: VendorService, action: ActionQueue
) -> ActionQueue:
    """On any failure the action stays 'approved' with an error recorded,
    rather than silently losing the approval decision."""
    message = action.payload.get("message_draft")
    vendor_id = action.payload.get("vendor_id")
    vendor = vendor_service.get(vendor_id) if vendor_id else None

    if not message or vendor is None or not vendor.whatsapp_number:
        return service.mark_error(action.id, "Missing message draft or vendor WhatsApp number.")

    try:
        WhatsAppService().send_message(message)
    except WhatsAppSendError as exc:
        return service.mark_error(action.id, str(exc))

    return service.mark_executed(action.id)
