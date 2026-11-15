# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
from .common import BASE_URL, FAKE_KEY, UniomTestCase


class TestInboundWebhook(UniomTestCase):
    def setUp(self):
        super().setUp()
        self.connection = self.env["uniom.connection"].create(
            {"name": "Inbound Test", "base_url": BASE_URL, "api_key": FAKE_KEY}
        )

    def _update(self, **kwargs):
        message = {
            "message_id": 5,
            "text": "سلام، سفارشم کجاست؟",
            "chat": {"id": "+989123456789", "type": "private"},
            "from": {"id": 15, "first_name": "Sara"},
        }
        message.update(kwargs)
        return {"update_id": 1, "message": message}

    def test_known_phone_matches_partner(self):
        partner = self.env["res.partner"].create(
            {"name": "Sara Known", "phone": "+989123456789"}
        )
        self.connection._process_inbound_update(self._update())
        message = self.env["uniom.message"].search(
            [("direction", "=", "in")], limit=1
        )
        self.assertEqual(message.partner_id, partner)
        self.assertEqual(message.chat_id, "+989123456789")
        self.assertIn("سفارش", message.body)

    def test_unknown_sender_creates_partner(self):
        self.connection._process_inbound_update(self._update())
        partner = self.env["res.partner"].search([("phone", "=", "+989123456789")], limit=1)
        self.assertTrue(partner)
        self.assertEqual(partner.name, "Sara")

    def test_no_create_when_disabled(self):
        self.connection.inbound_create_partner = False
        result = self.connection._process_inbound_update(self._update())
        self.assertFalse(result)

    def test_explicit_chat_id_wins(self):
        partner = self.env["res.partner"].create(
            {"name": "Channel Person", "uniom_chat_id": "@wholesale"}
        )
        update = self._update(chat={"id": "@wholesale", "type": "channel"}, text="hello")
        self.connection._process_inbound_update(update)
        message = self.env["uniom.message"].search([("direction", "=", "in")], limit=1)
        self.assertEqual(message.partner_id, partner)

    def test_non_message_update_ignored(self):
        self.assertFalse(self.connection._process_inbound_update({"update_id": 2}))
