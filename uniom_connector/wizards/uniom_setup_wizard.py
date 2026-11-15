# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Login-style onboarding: paste your Uniom API key, press Connect — the
gateway answers with the account name (getMe), inbound delivery is started
in the chosen mode, and the conversation list is seeded from getDialogs."""

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.uniom_tools import (
    DEFAULT_BASE_URL,
    UniomAPIError,
    validate_public_http_url,
)

_logger = logging.getLogger(__name__)

class UniomSetupWizard(models.TransientModel):
    _name = "uniom.setup.wizard"
    _description = "Connect Uniom Account"

    api_key = fields.Char(
        required=True,
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
    inbound_mode = fields.Selection(
        [("webhook", "Webhook (instant)"), ("polling", "Polling (works everywhere)")],
        string="Receive Messages Via",
        default="polling",
        required=True,
        help="Webhook is instant but needs a publicly reachable Odoo; "
        "polling fetches new messages every minute and works behind NAT.",
    )
    platform = fields.Selection(
        [
            ("bale", "Bale"),
            ("rubika", "Rubika"),
            ("eitaa", "Eitaa"),
            ("soroushplus", "Soroush+"),
            ("telegram", "Telegram"),
            ("other", "Other"),
        ],
        string="Messenger",
        help="Which messenger this API key belongs to.",
    )
    base_url_is_public = fields.Boolean(compute="_compute_base_url_is_public")

    @api.depends("base_url")
    def _compute_base_url_is_public(self):
        for wizard in self:
            base = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("web.base.url", "")
                .rstrip("/")
            )
            try:
                validate_public_http_url(base, resolve_dns=False)
            except Exception:  # noqa: BLE001 - structural check only
                wizard.base_url_is_public = False
            else:
                wizard.base_url_is_public = bool(base)

    def action_connect(self):
        self.ensure_one()
        connection = self.env["uniom.connection"].create(
            {
                "name": self.name or _("Uniom Account"),
                "base_url": self.base_url,
                "api_key": self.api_key,
                "inbound_mode": self.inbound_mode,
                "platform": self.platform or False,
            }
        )
        try:
            result = connection._call("getMe") or {}
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
        notes = []
        if self.inbound_mode == "polling":
            err = connection._friendly_call("action_start_polling")
            if err:
                _logger.warning("Uniom: polling start failed for %s: %s", display, err)
                notes.append(_("Polling could not be started: %s", err))
        else:
            err = connection._friendly_call("action_register_webhook")
            if err:
                _logger.warning("Uniom: webhook register failed for %s: %s", display, err)
                poll_err = connection._friendly_call("action_start_polling")
                if poll_err:
                    notes.append(
                        _("Webhook registration failed (%s); polling could not be started either (%s).", err, poll_err)
                    )
                else:
                    notes.append(
                        _("Webhook registration failed (%s); polling was started instead.", err)
                    )
        err = connection._friendly_call("action_sync_dialogs")
        if err:
            _logger.warning("Uniom: dialog sync failed for %s: %s", display, err)
            notes.append(_("Conversations could not be synchronized yet: %s", err))
        if notes:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Connected as %s", display),
                    "message": " ".join(str(note) for note in notes),
                    "type": "warning",
                    "sticky": True,
                    "next": {
                        "type": "ir.actions.act_window",
                        "name": _("Uniom Connection"),
                        "res_model": "uniom.connection",
                        "res_id": connection.id,
                        "view_mode": "form",
                        "target": "current",
                    },
                },
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("Uniom Connection"),
            "res_model": "uniom.connection",
            "res_id": connection.id,
            "view_mode": "form",
            "target": "current",
        }
