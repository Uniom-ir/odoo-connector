# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Queue semantics: send, retry-with-backoff, 429 retry-after, 504
no-retry, permanent failure, retries exhausted."""

from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase

from odoo.addons.uniom_connector.models import uniom_message as uniom_message_module
from odoo.addons.uniom_connector.models.uniom_tools import UniomAPIError

from .common import BASE_URL, FAKE_KEY, FakeResponse, error_response, ok_response, patched_transport


class TestQueue(TransactionCase):
    def setUp(self):
        super().setUp()
        self.connection = self.env["uniom.connection"].create(
            {"name": "Queue Test", "base_url": BASE_URL, "api_key": FAKE_KEY}
        )

    def _message(self, **kwargs):
        values = {
            "connection_id": self.connection.id,
            "chat_id": "+989120000001",
            "body": "Test message",
        }
        values.update(kwargs)
        return self.env["uniom.message"].create(values)

    def _raise(self, error):
        def raiser(*args, **kwargs):
            raise error
        return raiser

    def test_successful_send_records_message_id(self):
        message = self._message()
        with patched_transport([FakeResponse(ok_response({"message_id": 555}))]):
            message._send_message()
        self.assertEqual(message.state, "sent")
        self.assertEqual(message.uniom_message_id, 555)
        self.assertTrue(message.date_sent)

    def test_permanent_error_marks_failed_without_retry(self):
        message = self._message()
        with patched_transport(
            [FakeResponse(error_response(400, "Bad Request: chat not found"), status_code=400)]
        ):
            message._send_message()
        self.assertEqual(message.state, "error")
        self.assertIn("chat not found", message.error_message)
        self.assertFalse(message.next_attempt)

    def test_429_schedules_retry_with_retry_after(self):
        message = self._message()
        with patched_transport(
            [FakeResponse(
                error_response(429, "Too Many Requests", {"retry_after": 1800}), status_code=429
            )]
        ):
            message._send_message()
        self.assertEqual(message.state, "outgoing")
        self.assertEqual(message.retry_count, 1)
        self.assertGreaterEqual(
            message.next_attempt, fields.Datetime.now() + timedelta(minutes=29)
        )

    def test_504_never_retries(self):
        message = self._message()
        with patched_transport(
            [FakeResponse(error_response(504, "Gateway Timeout"), status_code=504)]
        ):
            message._send_message()
        self.assertEqual(message.state, "sent")
        self.assertIn("unknown", message.error_message)
        self.assertFalse(message.next_attempt)

    def test_retries_exhausted_marks_error(self):
        message = self._message()
        message.retry_count = uniom_message_module.MAX_ATTEMPTS
        with patched_transport(
            [FakeResponse(error_response(503, "Service Unavailable"), status_code=503)]
        ):
            message._send_message()
        self.assertEqual(message.state, "error")

    def test_cron_only_picks_due_messages(self):
        due = self._message()
        later = self._message(next_attempt=fields.Datetime.now() + timedelta(hours=1))
        canceled = self._message(state="canceled")
        with patched_transport([FakeResponse(ok_response({"message_id": 9}))]):
            self.env["uniom.message"]._cron_process_queue()
        self.assertEqual(due.state, "sent")
        self.assertEqual(later.state, "outgoing")
        self.assertEqual(canceled.state, "canceled")

    def test_edit_message_updates_in_place(self):
        message = self._message(state="sent", uniom_message_id=777)
        with patched_transport([FakeResponse(ok_response({"message_id": 777}))]) as transport:
            message._edit_message("new price: 200")
        self.assertEqual(message.body, "new price: 200")
        self.assertEqual(message.edit_count, 1)
        self.assertEqual(
            transport.calls[0]["json"]["message_id"], 777,
        )

    def test_edit_failure_falls_back_to_new_message(self):
        message = self._message(state="sent", uniom_message_id=777)
        with patched_transport([
            FakeResponse(error_response(400, "Bad Request: message to edit not found"), status_code=400),
            FakeResponse(ok_response({"message_id": 778})),
        ]) as transport:
            message._edit_message("new price: 300")
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(transport.calls[1]["json"]["text"], "new price: 300")
        new_sent = self.env["uniom.message"].search([("uniom_message_id", "=", 778)])
        self.assertTrue(new_sent)

    def test_auth_error_is_permanent(self):
        message = self._message()
        with patched_transport(
            [FakeResponse(error_response(401, "Unauthorized: invalid token"), status_code=401)]
        ):
            message._send_message()
        self.assertEqual(message.state, "error")

    def test_uniom_api_error_defaults(self):
        flood = UniomAPIError("flood", error_code=429, retry_after=10)
        self.assertTrue(flood.transient)
        server = UniomAPIError("boom", error_code=503)
        self.assertTrue(server.transient)
        gateway_timeout = UniomAPIError("unknown", error_code=504)
        self.assertFalse(gateway_timeout.transient)
        bad_request = UniomAPIError("nope", error_code=400)
        self.assertFalse(bad_request.transient)
