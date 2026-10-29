# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Two-field, login-style onboarding: paste your Uniom API key, press
Connect — the gateway answers with the account name (getMe) and the
connection is ready."""

import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.uniom_tools import DEFAULT_BASE_URL, UniomAPIError


class UniomSetupWizard(models.TransientModel):
    _name = "uniom.setup.wizard"
    _description = "Connect Uniom Account"

    api_key = fields.Char(
        required=True,
        password="True",
        help="Create one in your Uniom dashboard: Account → API Keys "
        "(uniom_... — one key per messenger account).",
    )
    base_url = fields.Char(
        string="Gateway URL",
        default=lambda self: self.env["ir.config_parameter"].sudo().get_param(
            "uniom_connector.default_base_url", DEFAULT_BASE_URL
        ),
        required=True,
    )
    name = fields.Char(
        string="Label (optional)",
        help="How this connection should be listed in Odoo. Leave empty to "
        "use the account name reported by the gateway.",
    )

    def action_connect(self):
        self.ensure_one()
        connection = self.env["uniom.connection"].create(
            {
                "name": self.name or _("Uniom Account"),
                "base_url": self.base_url,
                "api_key": self.api_key,
            }
        )
        try:
            result = connection._call("getMe")
        except UniomAPIError as error:
            # rollback removes the just-created connection: nothing partial
            # survives a failed "login"
            raise UserError(_(
                "Could not connect to Uniom: %s\nCheck the API key and try again.",
                str(error.args[0]) if error.args else str(error),
            )) from error
        display = (
            result.get("title")
            or result.get("first_name")
            or result.get("username")
            or _("Account #%s", result.get("id"))
        )
        connection.write(
            {
                "account_display": display,
                "account_details": json.dumps(result, indent=2, sort_keys=True),
            }
        )
        if not self.name:
            connection.name = display
        return {
            "type": "ir.actions.act_window",
            "name": _("Uniom Connection"),
            "res_model": "uniom.connection",
            "res_id": connection.id,
            "view_mode": "form",
            "target": "current",
        }
