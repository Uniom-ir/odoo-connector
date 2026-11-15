# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""End-to-end event tests with a mocked transport: confirming a sale order
posts a rendered message to the customer's canonical phone."""

from .common import BASE_URL, FAKE_KEY, FakeResponse, UniomTestCase, ok_response, patched_transport


class TestSaleOrderEvent(UniomTestCase):
    def setUp(self):
        super().setUp()
        self.connection = self.env["uniom.connection"].create(
            {"name": "Event Test", "base_url": BASE_URL, "api_key": FAKE_KEY}
        )
        self.partner = self.env["res.partner"].create(
            {"name": "Sara Customer", "phone": "09123456789"}
        )
        self.product = self.env["product.product"].create(
            {"name": "Test Service", "list_price": 100, "type": "service"}
        )

    def _create_order(self, partner=None):
        return self.env["sale.order"].create(
            {
                "partner_id": (partner or self.partner).id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 2,
                            "price_unit": 100,
                        },
                    )
                ],
            }
        )

    def test_confirm_sends_canonical_phone_message(self):
        order = self._create_order()
        with patched_transport([FakeResponse(ok_response({"message_id": 1001}))]) as transport:
            order.action_confirm()
        messages = self.env["uniom.message"].search(
            [("record_res_model", "=", "sale.order"), ("record_res_id", "=", order.id)]
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages.chat_id, "+989123456789")
        self.assertEqual(messages.state, "sent")
        self.assertIn("Sara Customer", messages.body)
        self.assertIn(order.name, messages.body)
        self.assertEqual(transport.calls[0]["json"]["chat_id"], "+989123456789")

    def test_opt_out_partner_gets_no_customer_message(self):
        opted_out = self.env["res.partner"].create(
            {"name": "Quiet Customer", "phone": "09121112233", "uniom_opt_out": True}
        )
        order = self._create_order(partner=opted_out)
        with patched_transport():
            order.action_confirm()
        messages = self.env["uniom.message"].search(
            [("record_res_model", "=", "sale.order"), ("record_res_id", "=", order.id)]
        )
        self.assertFalse(messages)

    def test_manual_channel_destinations_also_notified(self):
        rule = self.env.ref("uniom_connector.rule_sale_order_confirmed")
        rule.manual_chat_ids = "@myshop\n09123456789"
        order = self._create_order()
        with patched_transport([FakeResponse(ok_response())] * 2):
            order.action_confirm()
        chat_ids = self.env["uniom.message"].search(
            [("record_res_id", "=", order.id)]
        ).mapped("chat_id")
        # customer phone + @myshop (deduplicated: the phone matches)
        self.assertIn("+989123456789", chat_ids)
        self.assertIn("@myshop", chat_ids)
        self.assertEqual(len(chat_ids), 2)

    def test_master_switch_disables_events(self):
        self.env["ir.config_parameter"].sudo().set_bool("uniom_connector.enabled", False)
        order = self._create_order()
        with patched_transport() as transport:
            order.action_confirm()
        self.assertFalse(transport.calls)
        self.env["ir.config_parameter"].sudo().set_bool("uniom_connector.enabled", True)

    def test_no_connection_no_error(self):
        self.connection.active = False
        order = self._create_order()
        with patched_transport() as transport:
            order.action_confirm()  # must not raise
        self.assertFalse(transport.calls)


class TestProductPriceEdit(UniomTestCase):
    def setUp(self):
        super().setUp()
        self.connection = self.env["uniom.connection"].create(
            {"name": "Channel Test", "base_url": BASE_URL, "api_key": FAKE_KEY}
        )
        self.rule = self.env.ref("uniom_connector.rule_product_price_changed")
        self.rule.active = True
        self.rule.manual_chat_ids = "@shopchannel"

    def test_price_change_edits_previous_post(self):
        product = self.env["product.template"].create({"name": "Gadget", "list_price": 50})
        with patched_transport([FakeResponse(ok_response({"message_id": 61}))]):
            product.list_price = 60
        first = self.env["uniom.message"].search(
            [("rule_id", "=", self.rule.id), ("record_res_id", "=", product.id)]
        )
        self.assertEqual(len(first), 1)
        self.assertIn("60", first.body)
        first.uniom_message_id = "61"
        with patched_transport([FakeResponse(ok_response({"message_id": 61}))]) as transport:
            product.list_price = 75
        self.assertEqual(len(transport.calls), 1)
        self.assertIn("editMessageText", transport.calls[0]["url"])
        self.assertEqual(first.edit_count, 1)
        self.assertIn("75", first.body)
