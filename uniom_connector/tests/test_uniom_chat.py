# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Conversations: automatic session grouping and the thread reply box."""

from odoo.exceptions import UserError

from .common import BASE_URL, FAKE_KEY, FakeResponse, UniomTestCase, ok_response, patched_transport


class TestConversations(UniomTestCase):
    def setUp(self):
        super().setUp()
        self.connection = self.env["uniom.connection"].create(
            {"name": "Chat Test", "base_url": BASE_URL, "api_key": FAKE_KEY}
        )
        self.partner = self.env["res.partner"].create(
            {"name": "Sara Chat", "phone": "+989120000001"}
        )

    def _outbound(self, body="order confirmed"):
        return self.env["uniom.message"].create(
            {
                "connection_id": self.connection.id,
                "chat_id": "+989120000001",
                "partner_id": self.partner.id,
                "body": body,
            }
        )

    def test_outbound_message_opens_conversation(self):
        message = self._outbound()
        chat = self.env["uniom.chat"].search([("chat_id", "=", "+989120000001")])
        self.assertEqual(len(chat), 1)
        self.assertEqual(chat.partner_id, self.partner)
        self.assertEqual(message.chat_session_id, chat)
        self.assertEqual(chat.message_count, 1)
        self.assertEqual(chat.last_message_preview, "order confirmed")

    def test_inbound_reuses_conversation(self):
        self._outbound()
        self.connection._process_inbound_update(
            {
                "update_id": 1,
                "message": {
                    "message_id": 9,
                    "text": "مرسی، رسید",
                    "chat": {"id": "+989120000001", "type": "private"},
                    "from": {"id": 7, "first_name": "Sara"},
                },
            }
        )
        chat = self.env["uniom.chat"].search([("chat_id", "=", "+989120000001")])
        self.assertEqual(len(chat), 1)
        self.assertEqual(chat.message_count, 2)
        self.assertEqual(chat.last_message_preview, "مرسی، رسید")

    def test_inbound_raw_phone_id_does_not_split_thread(self):
        # gateway may report the chat id in a non-canonical spelling;
        # the thread key must still converge on one conversation
        self._outbound()
        self.connection._process_inbound_update(
            {
                "update_id": 2,
                "message": {
                    "message_id": 10,
                    "text": "ok",
                    "chat": {"id": "989120000001", "type": "private"},
                    "from": {"id": 7, "first_name": "Sara"},
                },
            }
        )
        chats = self.env["uniom.chat"].search(
            [("connection_id", "=", self.connection.id)]
        )
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats.chat_id, "+989120000001")
        self.assertEqual(chats.message_count, 2)

    def test_reply_box_sends_through_connection(self):
        self._outbound()
        chat = self.env["uniom.chat"].search([("chat_id", "=", "+989120000001")])
        chat.reply_body = "سفارش شما ارسال شد"
        with patched_transport([FakeResponse(ok_response({"message_id": 31}))]) as transport:
            chat.action_send_reply()
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0]["json"]["text"], "سفارش شما ارسال شد")
        self.assertFalse(chat.reply_body)
        self.assertEqual(chat.message_count, 2)
        self.assertEqual(chat.last_message_preview, "سفارش شما ارسال شد")

    def test_reply_requires_body(self):
        self._outbound()
        chat = self.env["uniom.chat"].search([("chat_id", "=", "+989120000001")])
        with self.assertRaises(UserError):
            chat.action_send_reply()

    def test_dashboard_reply_sends_and_reports(self):
        self._outbound()
        chat = self.env["uniom.chat"].search([("chat_id", "=", "+989120000001")])
        with patched_transport([FakeResponse(ok_response({"message_id": 88}))]) as transport:
            result = chat.action_send_dashboard_reply("سلام از داشبورد")
        self.assertEqual(result["state"], "sent")
        self.assertEqual(transport.calls[0]["json"]["text"], "سلام از داشبورد")
        self.assertEqual(chat.message_count, 2)
        self.assertEqual(chat.last_message_preview, "سلام از داشبورد")

    def test_dashboard_reply_empty_raises(self):
        self._outbound()
        chat = self.env["uniom.chat"].search([("chat_id", "=", "+989120000001")])
        with self.assertRaises(UserError):
            chat.action_send_dashboard_reply("   ")

    def test_display_name_search_uses_thread_identity(self):
        # the dashboard searches display_name server-side: the logical name
        # is composed of the contact, the messenger title and the chat id, so
        # the search override must match any of them (_rec_names_search)
        self._outbound()
        chat = self.env["uniom.chat"].search([("chat_id", "=", "+989120000001")])
        chat.messenger_title = "Sara Shop"
        found = self.env["uniom.chat"].search([("display_name", "ilike", "Sara S")])
        self.assertIn(chat, found)
        by_chat_id = self.env["uniom.chat"].search(
            [("display_name", "ilike", "+989120000001")]
        )
        self.assertIn(chat, by_chat_id)
        # negative operators AND the three terms: a chat matching only one of
        # them must be kept
        excluded = self.env["uniom.chat"].search(
            [("display_name", "not ilike", "Sara S")]
        )
        self.assertNotIn(chat, excluded)
