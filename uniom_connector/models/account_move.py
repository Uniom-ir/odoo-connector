# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        result = super().action_post()
        self.env["uniom.rule"]._apply_trigger("invoice_posted", self)
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
