# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Messenger rework: polling offset/dedupe, unread tracking, media labels,
presence mapping, dialog seeding and history backfill."""

from contextlib import contextmanager
from unittest.mock import patch

from odoo.exceptions import UserError

from odoo.addons.uniom_connector.models import uniom_connection as conn_module

from .common import (
    BASE_URL,
    FAKE_KEY,
    FakeResponse,
    UniomTestCase,
    error_response,
    ok_response,
    patched_transport,
)


def _update(update_id, **message_kwargs):
    message = {
        "message_id": 1000 + update_id,
        "text": "hello %s" % update_id,
        "date": 1794180000,
        "chat": {"id": 555001, "type": "private"},
        "from": {"id": 555001, "first_name": "Poll Peer"},
    }
    message.update(message_kwargs)
    return {"update_id": update_id, "message": message}


class _FakeDownload:
    def __init__(self, content):
        self.status_code = 200
        self.headers = {"Content-Type": "application/pdf"}
        self._content = content

    def iter_content(self, chunk_size=65536):
        yield self._content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@contextmanager
def _mock_download(content):
    with patch.object(conn_module.requests, "get",
                      lambda *a, **k: _FakeDownload(content)):
        yield


class TestPolling(UniomTestCase):
    def setUp(self):
        super().setUp()
        self.connection = self.env["uniom.connection"].create(
            {"name": "Poll Test", "base_url": BASE_URL, "api_key": FAKE_KEY,
             "inbound_mode": "polling"}
        )

    def test_poll_stores_page_and_advances_offset(self):
        script = [FakeResponse(ok_response([_update(10), _update(11)]))]
        with patched_transport(script) as transport:
            count = self.connection._poll_once()
        self.assertEqual(count, 2)
        self.assertEqual(self.connection.poll_offset, "12")
        self.assertFalse(self.connection.last_poll_error)
        self.assertTrue(self.connection.last_poll_at)
        payload = transport.calls[0]["json"]
        self.assertEqual(payload["limit"], 50)
        self.assertEqual(payload["timeout"], 0)
        stored = self.env["uniom.message"].search(
            [("connection_id", "=", self.connection.id)])
        self.assertEqual(len(stored), 2)
        self.assertEqual(
            sorted(stored.mapped("uniom_update_id")), ["10", "11"])
        # inbound rows start unread and open one thread
        self.assertFalse(any(stored.mapped("is_read")))
        chat = self.env["uniom.chat"].search(
            [("connection_id", "=", self.connection.id)])
        self.assertEqual(len(chat), 1)
        self.assertEqual(chat.unread_count, 2)

    def test_poll_replay_is_ignored(self):
        with patched_transport([FakeResponse(ok_response([_update(20)]))]):
            self.connection._poll_once()
        self.assertEqual(self.connection.poll_offset, "21")
        with patched_transport([FakeResponse(ok_response([_update(20)]))]):
            self.connection._poll_once()
        stored = self.env["uniom.message"].search(
            [("connection_id", "=", self.connection.id)])
        self.assertEqual(len(stored), 1)

    def test_own_echo_marks_outbound_and_read(self):
        self.connection.write(
            {"account_details": '{"id": 179605971, "first_name": "Me"}'})
        own = _update(21, **{"from": {"id": 179605971, "first_name": "Me"}})
        other = _update(22, **{"from": {"id": 555001, "first_name": "Peer"}})
        with patched_transport([FakeResponse(ok_response([own, other]))]):
            self.connection._poll_once()
        rows = {
            m.uniom_update_id: m
            for m in self.env["uniom.message"].search(
                [("connection_id", "=", self.connection.id)])
        }
        self.assertEqual(rows["21"].direction, "out")
        self.assertTrue(rows["21"].is_read)
        self.assertEqual(rows["22"].direction, "in")
        self.assertFalse(rows["22"].is_read)

    def test_direction_coerces_int_and_string_ids(self):
        self.connection.write({"account_details": '{"id": "555002"}'})
        cases = [
            ({"id": 555002}, "out"),
            ({"id": "555002"}, "out"),
            ({"id": 555003}, "in"),
            ({}, "in"),
        ]
        for author, expected in cases:
            with self.subTest(author=author):
                self.assertEqual(
                    self.connection._direction_for_sender({"from": author}),
                    expected,
                )
        self.assertEqual(self.connection._direction_for_sender({}), "in")
        self.assertEqual(
            self.connection._direction_for_sender(
                {"sender_chat": {"id": 555002}}),
            "out",
        )

    def test_poll_conflict_backs_off(self):
        script = [FakeResponse(
            error_response(409, "Conflict: webhook is active"), status_code=409)]
        with patched_transport(script):
            self.assertEqual(self.connection._poll_once(), 0)
        self.assertTrue(self.connection.last_poll_error)
        self.assertTrue(self.connection.poll_backoff_until)
        # while backing off, no request leaves the box
        with patched_transport(script) as transport:
            self.assertEqual(self.connection._poll_once(), 0)
        self.assertFalse(transport.calls)

    def test_start_polling_deletes_webhook_and_sets_mode(self):
        self.connection.inbound_mode = "webhook"
        with patched_transport(
            [FakeResponse(ok_response(True))]) as transport:
            self.connection.action_start_polling()
        self.assertEqual(self.connection.inbound_mode, "polling")
        self.assertIn("deleteWebhook", transport.calls[0]["url"])
        self.assertFalse(transport.calls[0]["json"]["drop_pending_updates"])

    def test_register_webhook_keeps_pending_updates(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "web.base.url", "https://odoo.example.com")
        with patched_transport(
            [FakeResponse(ok_response(True))]) as transport:
            self.connection.action_register_webhook()
        payload = transport.calls[0]["json"]
        self.assertIn("setWebhook", transport.calls[0]["url"])
        self.assertFalse(payload["drop_pending_updates"])
        self.assertEqual(self.connection.inbound_mode, "webhook")

    def test_webhook_replay_after_poll_is_ignored(self):
        with patched_transport([FakeResponse(ok_response([_update(30)]))]):
            self.connection._poll_once()
        self.assertFalse(self.connection._process_inbound_update(_update(30)))
        stored = self.env["uniom.message"].search(
            [("connection_id", "=", self.connection.id)])
        self.assertEqual(len(stored), 1)


class TestMediaInbound(UniomTestCase):
    def setUp(self):
        super().setUp()
        self.connection = self.env["uniom.connection"].create(
            {"name": "Media Test", "base_url": BASE_URL, "api_key": FAKE_KEY}
        )

    def test_photo_without_caption_gets_label(self):
        update = _update(
            40, text=None,
            photo=[{"file_id": "small", "file_size": 10},
                   {"file_id": "big", "file_size": 99}],
        )
        del update["message"]["text"]
        with patched_transport([FakeResponse(ok_response({}))]):
            # getFile answers without a file_path: no download, no crash
            self.assertTrue(self.connection._process_inbound_update(update))
        message = self.env["uniom.message"].search(
            [("connection_id", "=", self.connection.id)], limit=1)
        self.assertEqual(message.message_kind, "photo")
        self.assertTrue(message.body)

    def test_document_download_attaches_file(self):
        update = _update(
            41, text=None,
            document={"file_id": "doc1", "file_name": "price.pdf",
                      "mime_type": "application/pdf", "file_size": 4},
        )
        del update["message"]["text"]
        script = [FakeResponse(ok_response(
            {"file_id": "doc1", "file_path": "files/abc", "file_size": 4}))]
        with patched_transport(script):
            with _mock_download(b"%PDF"):
                self.assertTrue(self.connection._process_inbound_update(update))
        message = self.env["uniom.message"].search(
            [("connection_id", "=", self.connection.id)], limit=1)
        self.assertEqual(message.message_kind, "document")
        self.assertEqual(len(message.attachment_ids), 1)
        self.assertEqual(message.attachment_ids.name, "price.pdf")

    def test_location_label(self):
        update = _update(
            42, text=None,
            location={"latitude": 35.7, "longitude": 51.4},
        )
        del update["message"]["text"]
        with patched_transport():
            self.connection._process_inbound_update(update)
        message = self.env["uniom.message"].search(
            [("uniom_update_id", "=", "42")], limit=1)
        self.assertEqual(message.message_kind, "location")
        self.assertIn("35.7", message.body)

    def test_edited_message_updates_row(self):
        with patched_transport():
            self.connection._process_inbound_update(_update(43, text="v1"))
        message = self.env["uniom.message"].search(
            [("uniom_update_id", "=", "43")], limit=1)
        edited = {"update_id": 44, "edited_message": dict(
            _update(43, text="v2")["message"])}
        with patched_transport():
            self.assertTrue(self.connection._process_inbound_update(edited))
        self.assertEqual(message.body, "v2")
        self.assertEqual(message.edit_count, 1)
        self.assertEqual(
            self.env["uniom.message"].search_count(
                [("connection_id", "=", self.connection.id)]), 1)


class TestPresenceAndDialogs(UniomTestCase):
    def setUp(self):
        super().setUp()
        self.connection = self.env["uniom.connection"].create(
            {"name": "Presence Test", "base_url": BASE_URL, "api_key": FAKE_KEY}
        )
        partner = self.env["res.partner"].create(
            {"name": "Peer", "phone": "+989120000001"})
        self.chat = self.env["uniom.chat"].create(
            {"connection_id": self.connection.id, "chat_id": "+989120000001",
             "partner_id": partner.id, "chat_type": "private"})

    def test_presence_maps_label_and_timestamp(self):
        script = [FakeResponse(ok_response({
            "chat": {"id": 1, "type": "private"},
            "last_activity_at": "2026-11-09T00:01:52Z",
            "last_activity_label": "recently",
            "last_activity_is_exact": True,
        }))]
        with patched_transport(script):
            self.chat.action_sync_presence()
        self.assertEqual(self.chat.last_seen_label, "recently")
        self.assertTrue(self.chat.last_seen_is_exact)
        self.assertTrue(self.chat.last_seen_at)
        self.assertTrue(self.chat.presence_updated_at)

    def test_presence_failure_never_raises(self):
        script = [FakeResponse(
            error_response(400, "Bad Request: chat not found"), status_code=400)]
        with patched_transport(script):
            self.assertTrue(self.chat.action_sync_presence())

    def test_sync_dialogs_seeds_chats(self):
        script = [FakeResponse(ok_response([
            {"id": 777001, "type": "private", "first_name": "Sara",
             "last_name": "M", "username": "sara_m"},
            {"id": -1001, "type": "group", "title": "Shop Staff"},
        ]))]
        with patched_transport(script):
            self.connection.action_sync_dialogs()
        chats = self.env["uniom.chat"].search(
            [("connection_id", "=", self.connection.id),
             ("chat_id", "in", ["777001", "-1001"])])
        self.assertEqual(len(chats), 2)
        private = chats.filtered(lambda c: c.chat_id == "777001")
        self.assertEqual(private.messenger_title, "Sara M")
        self.assertEqual(private.messenger_username, "sara_m")
        self.assertEqual(private.chat_type, "private")
        group = chats.filtered(lambda c: c.chat_id == "-1001")
        self.assertEqual(group.messenger_title, "Shop Staff")
        self.assertTrue(self.connection.last_dialog_sync_at)

    def test_load_history_backfills_without_unread(self):
        script = [FakeResponse(ok_response([
            {"message_id": 9002, "date": 1794180002, "text": "newer",
             "chat": {"id": 555002, "type": "private"},
             "from": {"id": 555002, "first_name": "Peer"}},
            {"message_id": 9001, "date": 1794180001, "text": "older",
             "chat": {"id": 555002, "type": "private"},
             "from": {"id": 555002, "first_name": "Peer"}},
        ]))]
        chat = self.env["uniom.chat"].create(
            {"connection_id": self.connection.id, "chat_id": "555002",
             "chat_type": "private"})
        with patched_transport(script):
            result = chat.action_load_history(limit=10)
        self.assertEqual(result, {"loaded": 2, "fixed": 0})
        self.assertEqual(chat.unread_count, 0)
        self.assertEqual(
            sorted(chat.message_ids.mapped("uniom_message_id")),
            ["9001", "9002"])

    def test_load_history_reconciles_stored_directions(self):
        self.connection.write({"account_details": '{"id": 99}'})
        chat = self.env["uniom.chat"].create(
            {"connection_id": self.connection.id, "chat_id": "555003",
             "chat_type": "private"})
        stale = self.env["uniom.message"].create(
            {"connection_id": self.connection.id, "chat_session_id": chat.id,
             "direction": "in", "state": "sent", "chat_id": "555003",
             "body": "own echo stored wrong", "uniom_message_id": "9101",
             "is_read": True, "date_sent": "2026-01-01 00:00:00"})
        script = [FakeResponse(ok_response([
            {"message_id": 9101, "date": 1794180001, "text": "own echo stored wrong",
             "chat": {"id": 555003, "type": "private"},
             "from": {"id": 99, "first_name": "Me"}},
        ]))]
        with patched_transport(script):
            result = chat.action_load_history(limit=10)
        self.assertEqual(result, {"loaded": 0, "fixed": 1})
        self.assertEqual(stale.direction, "out")
        self.assertTrue(stale.is_read)
        self.assertEqual(chat.unread_count, 0)


class TestReadReceipts(UniomTestCase):
    def setUp(self):
        super().setUp()
        self.connection = self.env["uniom.connection"].create(
            {"name": "Read Test", "base_url": BASE_URL, "api_key": FAKE_KEY}
        )

    def test_mark_read_clears_badge_despite_gateway_404(self):
        with patched_transport():
            self.connection._process_inbound_update(_update(50))
        chat = self.env["uniom.chat"].search(
            [("connection_id", "=", self.connection.id)], limit=1)
        self.assertEqual(chat.unread_count, 1)
        # Bale self-chats answer 404 on markChatRead: badge clears anyway
        script = [FakeResponse(
            error_response(404, "Bad Request: Not Found"), status_code=404)]
        with patched_transport(script):
            self.assertTrue(chat.action_mark_read())
        self.assertEqual(chat.unread_count, 0)

    def test_permanent_send_failure_raises_activity(self):
        partner = self.env["res.partner"].create({"name": "Fail Customer"})
        message = self.env["uniom.message"].create(
            {"connection_id": self.connection.id, "direction": "out",
             "state": "outgoing", "chat_id": "@nowhere",
             "partner_id": partner.id, "body": "hi",
             "record_res_model": "res.partner", "record_res_id": partner.id,
             "record_name": partner.name})
        script = [FakeResponse(
            error_response(400, "Bad Request: chat not found"), status_code=400)]
        with patched_transport(script):
            message._send_message()
        self.assertEqual(message.state, "error")
        activities = self.env["mail.activity"].search(
            [("res_model", "=", "res.partner"), ("res_id", "=", partner.id)])
        self.assertTrue(activities)
        self.assertIn("Uniom delivery failed", activities[0].summary)


class TestDashboardAttachment(UniomTestCase):
    def setUp(self):
        super().setUp()
        self.connection = self.env["uniom.connection"].create(
            {"name": "Attach Test", "base_url": BASE_URL, "api_key": FAKE_KEY}
        )
        self.chat = self.env["uniom.chat"].create(
            {"connection_id": self.connection.id, "chat_id": "555009",
             "chat_type": "private"})

    def _upload(self, **kwargs):
        values = {"name": "note.txt", "raw": b"hello",
                  "mimetype": "text/plain", "res_model": "uniom.chat",
                  "res_id": self.chat.id}
        values.update(kwargs)
        return self.env["ir.attachment"].create(values)

    def test_own_upload_sends_and_relinks(self):
        attachment = self._upload()
        script = [FakeResponse(ok_response({"message_id": 31337}))]
        with patched_transport(script) as transport:
            result = self.chat.action_send_dashboard_attachment(
                attachment.id, caption="see attached")
        self.assertEqual(result["state"], "sent")
        self.assertIn("sendDocument", transport.calls[0]["url"])
        self.assertEqual(attachment.res_model, "uniom.message")
        message = self.env["uniom.message"].search(
            [("chat_session_id", "=", self.chat.id),
             ("direction", "=", "out")], limit=1)
        self.assertEqual(message.attachment_id, attachment)
        self.assertEqual(message.message_kind, "document")

    def test_foreign_record_attachment_rejected(self):
        partner = self.env["res.partner"].create({"name": "Victim"})
        attachment = self._upload(res_model="res.partner", res_id=partner.id)
        with patched_transport():
            with self.assertRaises(UserError):
                self.chat.action_send_dashboard_attachment(attachment.id)
        self.assertEqual(attachment.res_model, "res.partner")

    def test_other_chat_attachment_rejected(self):
        other = self.env["uniom.chat"].create(
            {"connection_id": self.connection.id, "chat_id": "555010"})
        attachment = self._upload(res_id=other.id)
        with patched_transport():
            with self.assertRaises(UserError):
                self.chat.action_send_dashboard_attachment(attachment.id)

    def test_other_user_attachment_rejected(self):
        other_user = self.env["res.users"].create(
            {"name": "Other", "login": "other_attach_user"})
        attachment = self._upload()
        attachment.sudo().write({"create_uid": other_user.id})
        with patched_transport():
            with self.assertRaises(UserError):
                self.chat.action_send_dashboard_attachment(attachment.id)


class TestDiscussBridge(UniomTestCase):
    def setUp(self):
        super().setUp()
        self.connection = self.env["uniom.connection"].create(
            {"name": "Discuss Test", "base_url": BASE_URL, "api_key": FAKE_KEY}
        )
        partner = self.env["res.partner"].create({"name": "Bridge Peer"})
        self.chat = self.env["uniom.chat"].create(
            {"connection_id": self.connection.id, "chat_id": "555020",
             "chat_type": "private", "partner_id": partner.id})

    def test_mirror_post_no_echo_loop(self):
        with patched_transport():
            self.connection._process_inbound_update(_update(60))
        chat = self.env["uniom.chat"].search(
            [("connection_id", "=", self.connection.id),
             ("chat_id", "=", "555001")], limit=1)
        channel = chat.discuss_channel_id
        self.assertTrue(channel)
        self.assertEqual(len(channel.message_ids), 1)
        # the mirror post must not forward back out (would double-send)
        outbound = self.env["uniom.message"].search(
            [("chat_session_id", "=", chat.id), ("direction", "=", "out")])
        self.assertFalse(outbound)

    def test_discuss_reply_forwards_plain_text(self):
        channel = self.chat._ensure_discuss_channel()
        script = [FakeResponse(ok_response({"message_id": 424242}))]
        admin = self.env.ref("base.user_admin")
        with patched_transport(script) as transport:
            channel.message_post(
                body="<p>hello-from-discuss</p>",
                author_id=admin.partner_id.id,
                message_type="comment", subtype_xmlid="mail.mt_comment")
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0]["json"]["text"], "hello-from-discuss")
        message = self.env["uniom.message"].search(
            [("chat_session_id", "=", self.chat.id),
             ("direction", "=", "out")], limit=1)
        self.assertEqual(message.body, "hello-from-discuss")

    def test_notification_posts_ignored(self):
        channel = self.chat._ensure_discuss_channel()
        with patched_transport() as transport:
            channel.message_post(
                body="joined the channel",
                message_type="notification", subtype_xmlid="mail.mt_comment")
        self.assertFalse(transport.calls)

    def test_odoobot_answers_never_forwarded(self):
        channel = self.chat._ensure_discuss_channel()
        odoobot = self.env.ref("base.partner_root")
        with patched_transport() as transport:
            channel.message_post(
                body="<p>I can help with that!</p>",
                author_id=odoobot.id,
                message_type="comment", subtype_xmlid="mail.mt_comment")
        self.assertFalse(transport.calls)
