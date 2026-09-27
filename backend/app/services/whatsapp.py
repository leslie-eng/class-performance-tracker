"""WhatsApp delivery. Only the scheduler/admin jobs call this, never a user request.

Meta requires an approved template for business-initiated messages outside the
24h customer-service window. Set WHATSAPP_LAG_TEMPLATE to an approved template
with one body parameter and every nudge is sent through it; otherwise a plain
text message is sent, which only works after the member has messaged the bot.
"""

import logging
from typing import Protocol

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

GRAPH_API = "https://graph.facebook.com/v21.0"


class WhatsAppError(Exception):
    pass


class WhatsAppSender(Protocol):
    def send(self, phone_number: str, message: str) -> None: ...


class ConsoleSender:
    """Development sender: logs instead of sending."""

    def send(self, phone_number: str, message: str) -> None:
        log.info("[whatsapp -> %s] %s", phone_number, message)


class MetaCloudSender:
    def __init__(self, token: str, phone_number_id: str, template: str | None = None):
        self.token = token
        self.url = f"{GRAPH_API}/{phone_number_id}/messages"
        self.template = template

    def send(self, phone_number: str, message: str) -> None:
        to = phone_number.lstrip("+")
        if self.template:
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "template",
                "template": {
                    "name": self.template,
                    "language": {"code": "en"},
                    "components": [{"type": "body", "parameters": [{"type": "text", "text": message}]}],
                },
            }
        else:
            payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": message}}
        try:
            resp = httpx.post(self.url, json=payload, headers={"Authorization": f"Bearer {self.token}"}, timeout=15)
        except httpx.HTTPError as e:
            raise WhatsAppError(str(e)) from e
        if resp.status_code >= 400:
            raise WhatsAppError(f"HTTP {resp.status_code}: {resp.text[:300]}")


def get_sender() -> WhatsAppSender:
    s = get_settings()
    if s.whatsapp_provider == "meta":
        if not (s.whatsapp_token and s.whatsapp_phone_number_id):
            raise RuntimeError("WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID are required for the meta provider")
        return MetaCloudSender(s.whatsapp_token, s.whatsapp_phone_number_id, s.whatsapp_lag_template)
    return ConsoleSender()
