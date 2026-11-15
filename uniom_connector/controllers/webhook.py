# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Inbound webhook receiver for Uniom (Telegram-shaped updates).

Register the URL from a connection form (Register Webhook button); Uniom
then pushes every incoming message here with a shared secret in the
``X-Telegram-Bot-Api-Secret-Token`` header.

The secret is verified *before* the payload is parsed, unknown connections
and bad secrets answer identically (404, no enumeration oracle), and the
body size is capped — Telegram-style updates are tiny.
"""

import hmac
import logging

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
MAX_BODY_BYTES = 1024 * 1024  # updates are small; 1 MiB is already generous


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
        # cheap size guard before any parsing
        content_length = request.httprequest.content_length or 0
        if content_length > MAX_BODY_BYTES:
            return request.make_json_response({"ok": False, "error": "too large"}, status=413)

        connection = request.env["uniom.connection"].sudo().browse(connection_id).exists()
        provided = (request.httprequest.headers.get(SECRET_HEADER, "") or "").encode("utf-8")
        expected = (connection.webhook_secret or "").encode("utf-8") if connection else b"none"
        if (
            not connection
            or not connection.active
            or not connection.webhook_secret
            or not hmac.compare_digest(provided, expected)
        ):
            # same answer for "unknown" and "wrong secret": 404, no oracle
            _logger.warning("Uniom webhook: refused call for connection %s", connection_id)
            return request.make_json_response({"ok": False, "error": "not found"}, status=404)

        try:
            update = request.get_json_data()
        except Exception:  # noqa: BLE001 - malformed body
            update = None
        if not isinstance(update, dict):
            return request.make_json_response({"ok": False, "error": "invalid payload"}, status=400)

        try:
            # a broken update (or a duplicate racing the polling cron) must
            # not abort the request transaction: roll back just this attempt
            with request.env.cr.savepoint():
                connection._process_inbound_update(update)
        except Exception:  # noqa: BLE001 - always ACK so Uniom does not retry endlessly
            _logger.exception("Uniom webhook: processing failed for connection %s", connection_id)
        connection.sudo().write({"last_webhook_at": fields.Datetime.now()})
        return request.make_json_response({"ok": True})
