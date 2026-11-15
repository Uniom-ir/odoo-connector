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
    uniom_outgoing_side = fields.Selection(
        [("right", "Right"), ("left", "Left")],
        string="Own Messages Side",
        config_parameter="uniom_connector.outgoing_side",
        default="right",
        required=True,
        help="Which side of the conversation your own (outgoing) messages "
        "appear on. Incoming messages take the other side.",
    )
