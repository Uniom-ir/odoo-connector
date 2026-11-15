# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""The login-style Connect wizard: one key in, verified connection out."""

from odoo.exceptions import ValidationError

from .common import BASE_URL, FAKE_KEY, INVALID_KEY, FakeResponse, UniomTestCase, ok_response, patched_transport


class TestSetupWizard(UniomTestCase):
    def test_system_admin_inherits_manager(self):
        admin = self.env.ref("base.user_admin")
        self.assertTrue(admin.has_group("uniom_connector.group_uniom_manager"))
        self.assertTrue(admin.has_group("uniom_connector.group_uniom_user"))

    def test_connect_success_uses_gateway_identity(self):
        wizard = self.env["uniom.setup.wizard"].create(
            {"api_key": FAKE_KEY, "base_url": BASE_URL}
        )
        with patched_transport(
            [FakeResponse(ok_response({"id": 5, "first_name": "Bale — فروشگاه"}))]
        ):
            action = wizard.action_connect()
        connection = self.env["uniom.connection"].browse(action["res_id"])
        self.assertEqual(connection.account_display, "Bale — فروشگاه")
        self.assertEqual(connection.name, "Bale — فروشگاه")  # label auto-filled
        self.assertTrue(connection.active)

    def test_connect_custom_label(self):
        wizard = self.env["uniom.setup.wizard"].create(
            {"api_key": FAKE_KEY, "base_url": BASE_URL, "name": "Shop Bale"}
        )
        with patched_transport([FakeResponse(ok_response({"id": 6, "username": "shopbot"}))]):
            wizard.action_connect()
        connection = self.env["uniom.connection"].search([("name", "=", "Shop Bale")])
        self.assertEqual(len(connection), 1)

    def test_connect_rejects_non_uniom_key(self):
        wizard = self.env["uniom.setup.wizard"].create(
            {"api_key": INVALID_KEY, "base_url": BASE_URL}
        )
        with self.assertRaises(ValidationError):
            wizard.action_connect()
