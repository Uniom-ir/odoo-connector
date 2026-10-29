# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Inbound webhook receiver for Uniom (Telegram-shaped updates).

Register the URL from a connection form (Register Webhook button); Uniom
then pushes every incoming message here with a shared secret in the
``X-Telegram-Bot-Api-Secret-Token`` header.
"""

import hmac
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


class UniomWebhookController(http.Controller):
    @http.route(
        "/uniom/webhook/<int:connection_id>",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def uniom_webhook(self, connection_id, **kwargs):
        try:
            update = request.get_json_data()
        except Exception:  # noqa: BLE001 - malformed body
            update = None
        if not isinstance(update, dict):
            return request.make_json_response({"ok": False, "error": "invalid payload"}, status=400)

        connection = request.env["uniom.connection"].sudo().browse(connection_id).exists()
        if not connection or not connection.active:
            return request.make_json_response({"ok": False, "error": "unknown connection"}, status=404)

        provided = request.httprequest.headers.get(SECRET_HEADER, "")
        if not connection.webhook_secret or not hmac.compare_digest(provided, connection.webhook_secret):
            _logger.warning("Uniom webhook: bad secret for connection %s", connection_id)
            return request.make_json_response({"ok": False, "error": "forbidden"}, status=403)

        try:
            connection._process_inbound_update(update)
        except Exception:  # noqa: BLE001 - always ACK so Uniom does not retry endlessly
            _logger.exception("Uniom webhook: processing failed for connection %s", connection_id)
        return request.make_json_response({"ok": True})
