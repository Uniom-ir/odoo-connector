# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        result = super().action_confirm()
        self.env["uniom.rule"]._apply_trigger("sale_order_confirmed", self)
        return result

    def action_quotation_send(self):
        result = super().action_quotation_send()
        self.env["uniom.rule"]._apply_trigger("quotation_sent", self)
        return result

    def action_uniom_send(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Send via Uniom",
            "res_model": "uniom.send.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_active_model": self._name,
                "default_active_id": self.id,
            },
        }
