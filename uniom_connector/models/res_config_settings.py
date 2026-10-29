# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    uniom_enabled = fields.Boolean(
        string="Uniom Notifications Enabled",
        config_parameter="uniom_connector.enabled",
        default=True,
    )
    uniom_default_base_url = fields.Char(
        string="Uniom Gateway URL",
        config_parameter="uniom_connector.default_base_url",
        default="https://api.uniom.ir",
    )
