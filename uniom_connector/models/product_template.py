# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
from odoo import api, models

PRICE_FIELDS = ("list_price", "standard_price")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env["uniom.rule"]._apply_trigger("product_created", records)
        return records

    def write(self, vals):
        result = super().write(vals)
        if any(field in vals for field in PRICE_FIELDS):
            self.env["uniom.rule"]._apply_trigger("product_price_changed", self)
        return result
