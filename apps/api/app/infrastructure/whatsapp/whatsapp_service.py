"""Twilio WhatsApp Sandbox client -- the send side of the vendor-coordination flow (P6-A9).

Sandbox limitation (not a bug): Twilio's WhatsApp Sandbox can only send free-form
messages to a number that has already messaged into the sandbox (the "join <code>"
step), which opens a rolling 24-hour window. TWILIO_WHATSAPP_TO is fixed via env
var rather than per-vendor for this reason -- in the demo, the same real phone
plays "the vendor" regardless of which Vendor row is stored in the DB. A real
WhatsApp Business API sender (not the sandbox) would send to each vendor's own
whatsapp_number instead.
"""

from twilio.rest import Client

from app.core.settings import get_settings


class WhatsAppSendError(Exception):
    pass


class WhatsAppService:
    def __init__(self):
        settings = get_settings()
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            raise WhatsAppSendError("Twilio is not configured (TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN missing).")
        self._client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        self._from = settings.twilio_whatsapp_from
        self._to = settings.twilio_whatsapp_to

    def send_message(self, body: str) -> str:
        """Send `body` via the configured Twilio WhatsApp Sandbox. Returns the
        Twilio message SID on success. Raises WhatsAppSendError on failure --
        never lets a Twilio exception leak past this boundary."""
        if not self._from or not self._to:
            raise WhatsAppSendError("TWILIO_WHATSAPP_FROM/TWILIO_WHATSAPP_TO not configured.")
        try:
            message = self._client.messages.create(from_=self._from, to=self._to, body=body)
        except Exception as exc:
            raise WhatsAppSendError(str(exc)) from exc
        return message.sid
