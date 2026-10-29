# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
from odoo import models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def action_post(self):
        result = super().action_post()
        self.env["uniom.rule"]._apply_trigger("payment_received", self)
        return result
