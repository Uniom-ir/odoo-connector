# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
import json

from odoo.tests import HttpCase, tagged

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


@tagged("post_install", "-at_install")
class TestWebhookRoute(HttpCase):
    # the route writes rows; HttpCase defaults the registry to read-only
    _registry_readonly_enabled = False

    """The HTTP surface: secret check, size cap and ACK/retry semantics."""

    def setUp(self):
        super().setUp()
        self.connection = self.env["uniom.connection"].create(
            {
                "name": "Route Test",
                "base_url": BASE_URL,
                "api_key": FAKE_KEY,
                "webhook_secret": "route-secret",
            }
        )
        self.url = "/uniom/webhook/%s" % self.connection.id
        self.payload = {
            "update_id": 77,
            "message": {
                "message_id": 770,
                "text": "hello route",
                "chat": {"id": "+989120000077", "type": "private"},
                "from": {"id": 15, "first_name": "Route"},
            },
        }

    def test_missing_secret_is_indistinguishable_404(self):
        for url in (self.url, "/uniom/webhook/999999"):
            res = self.url_open(url, data="{}", headers={"Content-Type": "application/json"})
            self.assertEqual(res.status_code, 404, url)

    def test_valid_secret_stores_the_message(self):
        res = self.url_open(
            self.url,
            data=json.dumps(self.payload),
            headers={
                "Content-Type": "application/json",
                "X-Telegram-Bot-Api-Secret-Token": "route-secret",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(json.loads(res.content).get("ok"), True)
        message = self.env["uniom.message"].search(
            [("connection_id", "=", self.connection.id)], limit=1
        )
        self.assertEqual(message.body, "hello route")

    def test_oversized_body_is_rejected(self):
        # rejected before parsing, whichever layer answers first (our cap or
        # the server's own body limit) — the point is it is never processed
        res = self.url_open(
            self.url,
            data="x" * (1024 * 1024 + 10),
            headers={
                "Content-Type": "application/json",
                "X-Telegram-Bot-Api-Secret-Token": "route-secret",
            },
        )
        # the dispatcher refuses it before the payload is read
        self.assertEqual(res.status_code, 413)
        self.assertEqual(
            self.env["uniom.message"].search_count(
                [("connection_id", "=", self.connection.id)]
            ),
            0,
        )
