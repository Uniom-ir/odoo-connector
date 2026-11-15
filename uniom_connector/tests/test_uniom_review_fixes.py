# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Regression tests for the pre-release backend review findings."""
from unittest.mock import patch

from markupsafe import Markup

from odoo import fields

from odoo.addons.uniom_connector.models import uniom_connection as uniom_connection_module
from odoo.addons.uniom_connector.models.uniom_connection import UniomConnection

from .common import (
    BASE_URL,
    FAKE_KEY,
    FakeResponse,
    error_response,
    ok_response,
    patched_transport,
    UniomTestCase,
)


class FakeGetResponse:
    def __init__(self, content):
        self.status_code = 200
        self._content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, chunk_size=None):
        yield self._content


class TestReviewFixes(UniomTestCase):
    def setUp(self):
        super().setUp()
        self.connection = self.env["uniom.connection"].create(
            {"name": "Review Fixes", "base_url": BASE_URL, "api_key": FAKE_KEY}
        )

    def _update(self, update_id, chat_id, message_id, text="hello", edited=False):
        message = {
            "message_id": message_id,
            "text": text,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": 15, "first_name": "Sara"},
        }
        key = "edited_message" if edited else "message"
        return {"update_id": update_id, key: message}

    def test_edited_message_scoped_to_chat(self):
        self.connection._process_inbound_update(
            self._update(1, "+989121111111", 5, text="original A")
        )
        row_a = self.env["uniom.message"].search(
            [("chat_id", "=", "+989121111111")], limit=1
        )
        self.assertEqual(row_a.body, "original A")
        # same gateway message id, other chat: must not touch chat A's row
        self.connection._process_inbound_update(
            self._update(2, "+989122222222", 5, text="edited B", edited=True)
        )
        self.assertEqual(row_a.body, "original A")
        self.assertEqual(row_a.edit_count, 0)
        row_b = self.env["uniom.message"].search(
            [("chat_id", "=", "+989122222222")], limit=1
        )
        self.assertTrue(row_b)
        self.assertEqual(row_b.body, "edited B")

    def test_history_backfill_scoped_to_chat(self):
        partner_a = self.env["res.partner"].create({"name": "Hist A"})
        chat_a = self.env["uniom.chat"].create(
            {
                "connection_id": self.connection.id,
                "chat_id": "+989123333333",
                "partner_id": partner_a.id,
            }
        )
        self.env["uniom.message"].create(
            {
                "connection_id": self.connection.id,
                "chat_session_id": chat_a.id,
                "direction": "in",
                "state": "sent",
                "chat_id": "+989123333333",
                "partner_id": partner_a.id,
                "body": "row of chat A",
                "uniom_message_id": "42",
            }
        )
        partner_b = self.env["res.partner"].create({"name": "Hist B"})
        chat_b = self.env["uniom.chat"].create(
            {
                "connection_id": self.connection.id,
                "chat_id": "+989124444444",
                "partner_id": partner_b.id,
            }
        )
        page = [{"message_id": 42, "text": "row of chat B", "date": 1763000000}]
        with patched_transport([FakeResponse(ok_response(page))]):
            result = chat_b.action_load_history(limit=10)
        self.assertEqual(result["loaded"], 1)
        row_b = self.env["uniom.message"].search(
            [("chat_session_id", "=", chat_b.id)], limit=1
        )
        self.assertEqual(row_b.body, "row of chat B")
        self.assertEqual(
            self.env["uniom.message"].search_count(
                [("chat_session_id", "=", chat_a.id)]
            ),
            1,
        )

    def test_setup_wizard_webhook_refusal_falls_back_to_polling(self):
        warning = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "x", "message": "private URL", "type": "warning"},
        }
        wizard = self.env["uniom.setup.wizard"].create(
            {
                "base_url": BASE_URL,
                "api_key": FAKE_KEY,
                "inbound_mode": "webhook",
            }
        )
        script = [
            FakeResponse(ok_response({"id": 7, "first_name": "Uniom"})),
            FakeResponse(ok_response(True)),  # deleteWebhook (polling start)
            FakeResponse(ok_response([])),  # getDialogs
        ]
        with patched_transport(script), patch.object(
            UniomConnection, "action_register_webhook", return_value=warning
        ):
            result = wizard.action_connect()
        connection = self.env["uniom.connection"].search(
            [], order="id desc", limit=1
        )
        self.assertEqual(connection.inbound_mode, "polling")
        self.assertEqual(result["params"]["type"], "warning")
        self.assertIn("polling was started instead", result["params"]["message"])

    def test_poll_offset_holds_failed_update_for_retry(self):
        self.connection.inbound_mode = "polling"
        updates = [{"update_id": 1}, {"update_id": 2}, {"update_id": 3}]
        real_process = UniomConnection._process_inbound_update

        def flaky(connection, update):
            if update.get("update_id") == 2:
                raise RuntimeError("transient boom")
            return real_process(connection, update)

        with patched_transport([FakeResponse(ok_response(updates))]), patch.object(
            UniomConnection, "_process_inbound_update", flaky
        ):
            self.connection._poll_once()
        self.assertEqual(self.connection.poll_offset, "2")
        self.assertIn("retried", self.connection.last_poll_error)

    def test_poll_offset_skips_update_after_retry_bound(self):
        self.connection.inbound_mode = "polling"
        updates = [{"update_id": 1}, {"update_id": 2}, {"update_id": 3}]
        real_process = UniomConnection._process_inbound_update

        def always_fails(connection, update):
            if update.get("update_id") == 2:
                raise RuntimeError("permanent poison")
            return real_process(connection, update)

        with patched_transport([FakeResponse(ok_response(updates))]), patch.object(
            UniomConnection, "_process_inbound_update", always_fails
        ):
            for _ in range(5):
                self.connection._poll_once()
            # still holding for retry at the bound
            self.assertEqual(self.connection.poll_offset, "2")
            self.connection._poll_once()
        # past the bound: skipped loudly, polling advances
        self.assertEqual(self.connection.poll_offset, "4")
        self.assertFalse(self.connection.poll_failed_update_id)
        self.assertEqual(self.connection.poll_failed_streak, 0)
        self.assertIn("skipped", self.connection.last_poll_error)

    def test_photo_sync_caches_and_skips_when_fresh(self):
        partner = self.env["res.partner"].create({"name": "Photo P"})
        chat = self.env["uniom.chat"].create(
            {
                "connection_id": self.connection.id,
                "chat_id": "+989125555555",
                "partner_id": partner.id,
            }
        )
        script = [
            FakeResponse(ok_response({"last_activity_label": "recently"})),
            FakeResponse(
                ok_response({"photos": [[{"file_id": "F1", "file_size": 10}]]})
            ),
            FakeResponse(ok_response({"file_path": "p/x.jpg"})),
        ]
        get_calls = []
        with patched_transport(script), patch.object(
            uniom_connection_module.requests,
            "get",
            lambda *a, **k: get_calls.append(a) or FakeGetResponse(b"IMG"),
        ):
            chat.action_sync_presence()
            self.assertTrue(chat.messenger_photo)
            first_count = len(get_calls)
            self.assertEqual(first_count, 1)
            # second presence sync within the week must not re-download
            chat.action_sync_presence()
            self.assertEqual(len(get_calls), 1)

    def test_inbound_chatter_body_is_markup(self):
        chat = self.env["uniom.chat"].create(
            {
                "connection_id": self.connection.id,
                "chat_id": "+989126666666",
            }
        )
        body = self.connection._inbound_chatter_body("hi", "text", chat)
        self.assertIsInstance(body, Markup)
        self.assertIn("Open in Uniom Conversations", body)

    def test_friendly_call_normalizes_raise_and_return(self):
        with patched_transport([FakeResponse(ok_response({"id": 1}))]):
            self.assertIsNone(
                self.connection._friendly_call("action_test_connection")
            )
        with patched_transport(
            [FakeResponse(error_response(401, "Unauthorized"))]
        ):
            text = self.connection._friendly_call("action_test_connection")
        self.assertIn("rejected", text)

    def test_friendly_call_returns_raised_user_error(self):
        params = self.env["ir.config_parameter"].sudo()
        previous = params.get_str("web.base.url", "")
        params.set_str("web.base.url", "")
        try:
            text = self.connection._friendly_call("action_register_webhook")
        finally:
            params.set_str("web.base.url", previous)
        self.assertIn("web.base.url", text)
        # the wizard transaction stays usable afterwards
        self.connection.write({"notes": "still works"})

    def test_friendly_call_isolates_db_errors(self):
        def bad_sql(connection):
            connection.env.cr.execute("THIS IS NOT SQL")

        with patch.object(UniomConnection, "action_sync_dialogs", bad_sql):
            text = self.connection._friendly_call("action_sync_dialogs")
        self.assertIn("unexpectedly", text)
        # without the savepoint this raises InFailedSqlTransaction
        self.connection.write({"notes": "still works"})

    def test_states_cron_syncs_outbound_only(self):
        partner = self.env["res.partner"].create({"name": "States P"})
        out = self.env["uniom.message"].create(
            {
                "connection_id": self.connection.id,
                "direction": "out",
                "state": "sent",
                "chat_id": "+989127777777",
                "partner_id": partner.id,
                "body": "hi",
                "uniom_message_id": "9",
                "date_sent": fields.Datetime.now(),
            }
        )
        inbound = self.env["uniom.message"].create(
            {
                "connection_id": self.connection.id,
                "direction": "in",
                "state": "sent",
                "chat_id": "+989127777777",
                "partner_id": partner.id,
                "body": "hello",
                "uniom_message_id": "10",
            }
        )
        states = [{"request_index": 0, "seen_state": "read", "seen_count": 2}]
        with patched_transport([FakeResponse(ok_response(states))]) as transport:
            self.env["uniom.message"]._cron_sync_states()
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(out.seen_state, "read")
        self.assertEqual(out.seen_count, 2)
        self.assertNotEqual(inbound.seen_state, "read")
