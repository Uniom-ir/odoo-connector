# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
from odoo.tests import TransactionCase


class TestTemplate(TransactionCase):
    def test_render_placeholders(self):
        template = self.env["uniom.template"].create(
            {
                "name": "Partner greeting",
                "model_id": self.env.ref("base.model_res_partner").id,
                "body": "Hello {{ object.name }}, phone {{ object.mobile or 'n/a' }}",
            }
        )
        partner = self.env["res.partner"].create(
            {"name": "Sara Test", "mobile": "+989120000009"}
        )
        rendered = template._render_for(partner)
        self.assertEqual(rendered[partner.id], "Hello Sara Test, phone +989120000009")

    def test_render_invalid_model_raises(self):
        template = self.env["uniom.template"].create(
            {
                "name": "Partner only",
                "model_id": self.env.ref("base.model_res_partner").id,
                "body": "${object.name}",
            }
        )
        product = self.env["product.template"].create({"name": "Widget"})
        from odoo.exceptions import UserError

        with self.assertRaises(UserError):
            template._render_for(product)

    def test_rule_picks_language_template(self):
        rule = self.env.ref("uniom_connector.rule_sale_order_confirmed", raise_if_not_found=False)
        if not rule:
            self.skipTest("default rule data not loaded")
        # languages loaded with --load-language appear after post_init_hook
        self.env["uniom.template"]._link_language_templates()
        fa = self.env["res.lang"].search([("code", "=", "fa_IR")], limit=1)
        if not fa:
            self.skipTest("Persian language not activated in this database")
        partner = self.env["res.partner"].create({"name": "Test", "lang": "fa_IR"})
        order = self.env["sale.order"].new({"partner_id": partner.id})
        template = rule._get_template_for(order)
        self.assertEqual(template.lang_id, fa)

    def test_rule_falls_back_to_default_template(self):
        rule = self.env.ref("uniom_connector.rule_sale_order_confirmed", raise_if_not_found=False)
        if not rule:
            self.skipTest("default rule data not loaded")
        partner = self.env["res.partner"].create({"name": "Test", "lang": "en_US"})
        order = self.env["sale.order"].new({"partner_id": partner.id})
        template = rule._get_template_for(order)
        self.assertFalse(template.lang_id)
        self.assertEqual(template, rule.template_id)
