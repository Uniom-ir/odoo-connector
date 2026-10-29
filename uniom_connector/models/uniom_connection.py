# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Uniom connections: one API key of a Uniom account plus the gateway base
URL. Each key is bound to exactly one messenger credential (Bale, Rubika,
Eitaa, Soroush+ or Telegram), so "which messenger" is a property of the
connection, not of each message."""

import json
import logging
import secrets

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .uniom_tools import DEFAULT_BASE_URL  # noqa: F401 (re-exported for other models)
from .uniom_tools import UniomAPIError, canonicalize_chat_id, validate_public_http_url

_logger = logging.getLogger(__name__)

API_KEY_RE_PREFIX = "uniom_"
# connection timeout, read timeout — the gateway streams long sends, so the
# read budget is generous but finite.
REQUEST_TIMEOUT = (10, 30)


class UniomConnection(models.Model):
    _name = "uniom.connection"
    _description = "Uniom Connection"
    _order = "sequence, id"
    _rec_names_search = "name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        index=True,
        help="Leave empty to make this connection available in every company.",
    )
    base_url = fields.Char(
        string="Gateway URL",
        default=lambda self: self.env["ir.config_parameter"].sudo().get_param(
            "uniom_connector.default_base_url", DEFAULT_BASE_URL
        ),
        required=True,
        help="Base URL of the Uniom Bot API. Use https://api.uniom.ir (Iran) "
        "or https://api.uniomi.ir (international mirror).",
    )
    api_key = fields.Char(
        string="API Key",
        copy=False,
        groups="uniom_connector.group_uniom_manager",
        help="The uniom_... key issued in your Uniom dashboard "
        "(Account → API Keys). Bound to one messenger account per key.",
    )
    account_display = fields.Char(
        string="Connected Account",
        readonly=True,
        copy=False,
        help="Account identity reported by the gateway (getMe).",
    )
    account_details = fields.Text(readonly=True, copy=False)
    webhook_secret = fields.Char(
        copy=False,
        default=lambda self: secrets.token_hex(16),
        groups="uniom_connector.group_uniom_manager",
        help="Secret sent back by Uniom in the "
        "X-Telegram-Bot-Api-Secret-Token header. Regenerate to invalidate.",
    )
    webhook_url = fields.Char(readonly=True, copy=False)
    webhook_registered = fields.Boolean(readonly=True, copy=False, default=False)
    inbound_create_partner = fields.Boolean(
        string="Create Contacts from Inbound Messages",
        default=True,
        help="When an incoming message cannot be matched to an existing "
        "contact, create one automatically.",
    )
    notes = fields.Text()

    # ------------------------------------------------------------------
    # Constraints & onchanges
    # ------------------------------------------------------------------
    @api.constrains("base_url")
    def _check_base_url(self):
        for connection in self:
            # Structural validation only (scheme/host syntax, no literal
            # private IPs): DNS is deliberately NOT resolved here, so
            # installations behind split-horizon DNS can still configure
            # their gateway. The full DNS-checked validation happens on
            # every request in _call().
            validate_public_http_url(connection.base_url, resolve_dns=False)

    @api.constrains("api_key")
    def _check_api_key(self):
        for connection in self:
            if connection.api_key and not connection.api_key.startswith(API_KEY_RE_PREFIX):
                raise ValidationError(
                    _(
                        "The Uniom API key must start with '%(prefix)s' — copy it "
                        "exactly as shown in your Uniom dashboard.",
                        prefix=API_KEY_RE_PREFIX,
                    )
                )

    @api.onchange("base_url")
    def _onchange_base_url(self):
        if self.base_url:
            try:
                validate_public_http_url(self.base_url, resolve_dns=False)
            except ValidationError as error:
                return {"warning": {"title": _("Invalid gateway URL"), "message": str(error)}}

    # ------------------------------------------------------------------
    # Low-level Bot API call
    # ------------------------------------------------------------------
    def _build_endpoint(self, method):
        self.ensure_one()
        base = (self.base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        return "%s/bot%s/%s" % (base, self.api_key, method)

    def _safe_error(self, error):
        """Transport error text with the API key (embedded in the request
        URL) removed — this string is logged and stored on messages visible
        to regular users."""
        text = str(error)
        if self.api_key:
            text = text.replace(self.api_key, "***")
            text = text.replace("bot" + self.api_key, "bot***")
        return text

    def _call(self, method, payload=None, files=None):
        """POST one Bot API method and return its ``result``.

        The full target URL is validated right before the request (scheme,
        host, resolved IPs — loopback/private/reserved refused) and redirects
        are disabled so the destination cannot change afterwards.

        Raises :class:`UniomAPIError` on any ``ok: false`` answer or network
        problem. ``transient`` errors are retry candidates for the queue.
        """
        self.ensure_one()
        if not self.api_key:
            raise UserError(_("The connection '%s' has no API key.", self.name))
        url = self._build_endpoint(method)
        validate_public_http_url(url)
        try:
            if files:
                response = requests.post(
                    url, data=payload or {}, files=files, timeout=REQUEST_TIMEOUT, allow_redirects=False
                )
            else:
                response = requests.post(
                    url, json=payload or {}, timeout=REQUEST_TIMEOUT, allow_redirects=False
                )
        except requests.RequestException as error:
            _logger.warning(
                "Uniom network error on %s (%s): %s",
                method, type(error).__name__, self._safe_error(error),
            )
            raise UniomAPIError(
                _("Network error while contacting Uniom: %s", self._safe_error(error)),
                transient=True,
            ) from error
        if 300 <= response.status_code < 400:
            # Redirects are never followed on purpose: the validated host
            # must also be the host that answers.
            raise UniomAPIError(
                _("Uniom answered with a redirect (HTTP %s) which is refused.", response.status_code),
                error_code=response.status_code,
            )
        try:
            data = response.json()
        except ValueError as error:
            raise UniomAPIError(
                _("Uniom answered with invalid JSON (HTTP %s).", response.status_code),
                error_code=response.status_code,
                transient=True,
            ) from error
        if not data.get("ok"):
            description = data.get("description") or response.reason or _("Unknown error")
            error_code = data.get("error_code") or response.status_code
            raise UniomAPIError(
                _("Uniom error %(code)s: %(description)s", code=error_code, description=description),
                error_code=error_code,
                retry_after=(data.get("parameters") or {}).get("retry_after"),
            )
        return data.get("result")

    # ------------------------------------------------------------------
    # Account actions
    # ------------------------------------------------------------------
    def action_test_connection(self):
        self.ensure_one()
        result = self._call("getMe") or {}
        display = (
            result.get("title")
            or result.get("first_name")
            or result.get("username")
            or _("Account #%s", result.get("id"))
        )
        self.write(
            {
                "account_display": display,
                "account_details": json.dumps(result, indent=2, sort_keys=True),
            }
        )
        return self._notify_success(
            _("Connected as %(account)s via %(url)s", account=display, url=self.base_url)
        )

    def action_regenerate_webhook_secret(self):
        for connection in self:
            connection.webhook_secret = secrets.token_hex(16)
            connection.webhook_registered = False
        return True

    def action_register_webhook(self):
        """Register this Odoo instance as the webhook target with Uniom."""
        for connection in self:
            base = (
                self.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")
            )
            if not base:
                raise UserError(
                    _("Set the 'web.base.url' system parameter to your Odoo base URL first.")
                )
            url = "%s/uniom/webhook/%s" % (base, connection.id)
            # Uniom refuses private hosts; validate on our side first so the
            # user gets an actionable message instead of a gateway 400.
            validate_public_http_url(url)
            connection._call(
                "setWebhook",
                {
                    "url": url,
                    "secret_token": connection.webhook_secret,
                    "allowed_updates": ["message", "edited_message", "channel_post"],
                    "drop_pending_updates": True,
                },
            )
            connection.write({"webhook_url": url, "webhook_registered": True})
        return self._notify_success(_("Webhook registered."))

    def action_delete_webhook(self):
        for connection in self:
            connection._call("deleteWebhook", {"drop_pending_updates": False})
            connection.write({"webhook_url": False, "webhook_registered": False})
        return True

    def _notify_success(self, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Uniom"), "message": message, "type": "success", "sticky": False},
        }

    # ------------------------------------------------------------------
    # Inbound updates (called by the webhook controller)
    # ------------------------------------------------------------------
    def _process_inbound_update(self, update):
        """Handle one Telegram-shaped update pushed by Uniom."""
        self.ensure_one()
        message = (
            update.get("message")
            or update.get("edited_message")
            or update.get("channel_post")
            or update.get("edited_channel_post")
        )
        if not message:
            return False
        chat = message.get("chat") or {}
        # canonicalize so inbound and reply paths converge on one thread key
        raw_chat_id = str(chat.get("id") or "")
        chat_id = canonicalize_chat_id(raw_chat_id) or raw_chat_id
        sender = message.get("from") or {}
        # messengers cap texts around 4096 chars; keep hostile overlong
        # payloads from flooding the log and the chatter
        text = (message.get("text") or message.get("caption") or "")[:4096]
        partner = self._find_partner_for_chat(chat_id, sender, chat)
        if not partner:
            return False
        self.env["uniom.message"].create(
            {
                "connection_id": self.id,
                "direction": "in",
                "state": "sent",
                "chat_id": chat_id,
                "partner_id": partner.id,
                "body": text,
                "date_sent": fields.Datetime.now(),
                # anchor inbound records to the connection's company (not the
                # superuser default) so multi-company users see their threads
                "company_id": (self.company_id or partner.company_id).id,
                "record_res_model": "res.partner",
                "record_res_id": partner.id,
                "record_name": partner.display_name,
            }
        )
        if hasattr(partner, "message_post"):
            partner.message_post(
                body=text,
                author_id=partner.id,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        return True

    def _find_partner_for_chat(self, chat_id, sender, chat):
        partner = self.env["res.partner"]
        if chat_id:
            explicit = partner.search([("uniom_chat_id", "=", chat_id)], limit=1)
            if explicit:
                return explicit
            if chat_id.startswith("+"):
                phone_like = partner.search(
                    ["|", ("mobile", "=", chat_id), ("phone", "=", chat_id)], limit=1
                )
                if phone_like:
                    return phone_like
        if not self.inbound_create_partner:
            return partner
        name = " ".join(
            part
            for part in (sender.get("first_name"), sender.get("last_name"))
            if part
        ) or sender.get("username") or chat.get("title") or _("Uniom contact %s", chat_id)
        values = {"name": name}
        if chat_id and chat_id.startswith("+"):
            values["mobile"] = chat_id
        else:
            values["uniom_chat_id"] = chat_id
        return partner.create(values)

    # ------------------------------------------------------------------
    # Tools for other models
    # ------------------------------------------------------------------
    @api.model
    def _get_default_connection(self, company=None):
        """First active connection usable by *company* (a specific one or any)."""
        domain = [("active", "=", True)]
        if company:
            domain += ["|", ("company_id", "=", False), ("company_id", "=", company.id)]
        return self.search(domain, limit=1)
