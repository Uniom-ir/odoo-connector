# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        result = super().button_validate()
        done = self.filtered(lambda picking: picking.state == "done")
        if done:
            self.env["uniom.rule"]._apply_trigger("picking_done", done)
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
