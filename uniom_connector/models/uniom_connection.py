# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Uniom connections: one API key of a Uniom account plus the gateway base
URL. Each key is bound to exactly one messenger credential (Bale, Rubika,
Eitaa, Soroush+ or Telegram), so "which messenger" is a property of the
connection, not of each message."""

import json
import logging
import mimetypes
import secrets
from datetime import datetime, timezone

import requests
from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html_escape

from markupsafe import Markup

from .uniom_tools import DEFAULT_BASE_URL  # noqa: F401 (re-exported for other models)
from .uniom_tools import UniomAPIError, canonicalize_chat_id, validate_public_http_url

_logger = logging.getLogger(__name__)

API_KEY_RE_PREFIX = "uniom_"
# connection timeout, read timeout — the gateway streams long sends, so the
# read budget is generous but finite.
REQUEST_TIMEOUT = (10, 30)

# getUpdates: the cron asks for a bounded page and returns immediately.
POLL_LIMIT = 50
# a 409 means a webhook is still registered on the gateway: stop hammering
# it and let the user finish the cutover.
POLL_CONFLICT_BACKOFF_MINUTES = 10
# a failing update holds the poll offset for retry; past this many
# consecutive failures it is skipped loudly so polling never wedges.
MAX_POLL_FAILED_STREAK = 5
# inbound files are streamed into ir.attachment; refuse anything above 20 MiB.
MAX_MEDIA_BYTES = 20 * 1024 * 1024
# update keys that carry a Message object, in the order they are looked up.
UPDATE_MESSAGE_KEYS = (
    "message",
    "edited_message",
    "channel_post",
    "edited_channel_post",
    "business_message",
    "edited_business_message",
)


def _datetime_from_timestamp(value):
    """Unix seconds (as sent by the Bot API) -> naive UTC datetime."""
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return False
    if timestamp <= 0:
        return False
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(tzinfo=None)


def _parse_iso_datetime(value):
    """ISO-8601 string (``...Z`` or offset-aware) -> naive UTC datetime."""
    if not value or not isinstance(value, str):
        return False
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            return fields.Datetime.to_datetime(value)
        except Exception:  # noqa: BLE001 - an unparsable label stays a label
            return False
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


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
        default=lambda self: self.env["ir.config_parameter"].sudo().get_str(
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
    credential_id = fields.Integer(
        readonly=True,
        copy=False,
        help="Messenger credential id on the Uniom management API, when "
        "this connection was created by the Link Messenger Account wizard.",
    )
    credential_phone = fields.Char(
        readonly=True,
        copy=False,
        help="Phone number (or bot identity) of the linked messenger account.",
    )
    credential_status = fields.Char(
        readonly=True,
        copy=False,
        help="State reported for the linked messenger credential.",
    )
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
    platform = fields.Selection(
        [
            ("bale", "Bale"),
            ("rubika", "Rubika"),
            ("eitaa", "Eitaa"),
            ("soroushplus", "Soroush+"),
            ("telegram", "Telegram"),
            ("other", "Other"),
        ],
        help="Which messenger this API key belongs to (pick it when you "
        "connect: the gateway does not report it via getMe).",
    )
    inbound_mode = fields.Selection(
        [("webhook", "Webhook"), ("polling", "Polling")],
        default="webhook",
        required=True,
        help="Webhook requires a publicly reachable Odoo; polling works "
        "behind NAT and is driven by the getUpdates cron.",
    )
    poll_offset = fields.Char(
        copy=False,
        help="Next getUpdates offset: the first update id the gateway may return.",
    )
    poll_allowed_updates = fields.Text(
        default='["message","edited_message","channel_post"]',
        help="JSON list of update types the polling cron subscribes to.",
    )
    last_poll_at = fields.Datetime(readonly=True, copy=False)
    last_poll_error = fields.Text(readonly=True, copy=False)
    poll_backoff_until = fields.Datetime(
        readonly=True,
        copy=False,
        help="Polling is paused until this moment (e.g. while a webhook is "
        "still registered on the gateway).",
    )
    poll_failed_update_id = fields.Char(
        readonly=True,
        copy=False,
        help="First update id that failed processing; the offset is held "
        "here for retry until it succeeds or exceeds the retry bound.",
    )
    poll_failed_streak = fields.Integer(
        readonly=True, copy=False, default=0,
        help="Consecutive polls the same update id failed; past the bound "
        "the poison update is skipped so polling never wedges.",
    )
    poll_dead_update = fields.Text(
        readonly=True,
        copy=False,
        help="Raw payload of the last skipped poison update (JSON), kept "
        "for support replay after the retry bound gave up on it.",
    )
    last_webhook_at = fields.Datetime(readonly=True, copy=False)
    webhook_pending_count = fields.Integer(readonly=True, copy=False)
    webhook_last_error = fields.Char(readonly=True, copy=False)
    last_dialog_sync_at = fields.Datetime(readonly=True, copy=False)
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
        try:
            validate_public_http_url(url)
        except ValidationError as error:
            # the validator echoes the URL, which embeds the API key —
            # redact before it reaches toasts/logs visible to non-managers
            raise ValidationError(self._safe_error(error)) from error
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
    # Management API (account linking)
    # ------------------------------------------------------------------
    def _mgmt_base_url(self):
        """Management API base derived from this record's gateway URL.

        The gateway's Bot API lives under ``/bot...``; the management routes
        (`/auth/...`, `/platforms/...`, `/api_keys`) live beside it on the
        same host. No host is ever hardcoded here.
        """
        self.ensure_one()
        base = (self.base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        if base.endswith("/bot"):
            base = base[: -len("/bot")]
        return base

    @staticmethod
    def _mgmt_error_text(data):
        """Extract the error text exactly like the Uniom panel's API client.

        Order: ``detail`` (string, or its ``message``/``description``),
        then top-level ``description``, ``message``, ``error``. A ``detail``
        array (FastAPI validation errors) overrides all of the above and is
        joined with commas, using each item's ``msg``/``message``.
        """
        if not isinstance(data, dict):
            return ""
        detail = data.get("detail")
        if isinstance(detail, str):
            message = detail
        elif isinstance(detail, dict):
            message = detail.get("message") or detail.get("description")
        else:
            message = None
        message = (
            message
            or data.get("description")
            or data.get("message")
            or data.get("error")
        )
        if isinstance(detail, list):
            message = ", ".join(
                (
                    item.get("msg") or item.get("message") or str(item)
                    if isinstance(item, dict)
                    else str(item)
                )
                for item in detail
            )
        return str(message) if message else ""

    def _mgmt_request(
        self, method, path, payload=None, session=None, csrf_token=None, extra_headers=None
    ):
        """Call one Uniom management endpoint and return its parsed JSON.

        The call runs through a :class:`requests.Session`, so the gateway's
        HttpOnly ``access_token``/``otp_client_id`` cookies travel with it.
        The CSRF token (from the login body) is sent as ``X-CSRF-Token`` on
        non-GET/HEAD/OPTIONS/TRACE calls only, mirroring the panel. No token
        is ever logged or placed on the connection record.
        """
        self.ensure_one()
        path = path if path.startswith("/") else "/" + path
        url = "%s%s" % (self._mgmt_base_url(), path)
        validate_public_http_url(url)
        method = (method or "POST").upper()
        headers = {"Accept": "application/json"}
        if csrf_token and method not in ("GET", "HEAD", "OPTIONS", "TRACE"):
            headers["X-CSRF-Token"] = csrf_token
        if extra_headers:
            headers.update(extra_headers)
        session = session or requests.Session()
        try:
            if method in ("GET", "HEAD"):
                response = session.request(
                    method,
                    url,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=False,
                )
            else:
                response = session.request(
                    method,
                    url,
                    json=payload or {},
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=False,
                )
        except requests.RequestException as error:
            raise UniomAPIError(
                _("Network error while contacting the Uniom management API: %s", error),
                transient=True,
            ) from error
        if 300 <= response.status_code < 400:
            # never follow a redirect: the validated host must answer itself
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
        if not 200 <= response.status_code < 300:
            message = self._mgmt_error_text(data) or response.reason or _("Unknown error")
            raise UniomAPIError(
                message,
                error_code=response.status_code,
            )
        if isinstance(data, dict) and data.get("ok") is False:
            code = data.get("error_code") or response.status_code
            message = self._mgmt_error_text(data) or _("Unknown error")
            raise UniomAPIError(
                message,
                error_code=code,
            )
        return data

    def _mgmt_call(
        self, path, payload=None, session=None, csrf_token=None, method="POST", headers=None
    ):
        """Call a management API path with the given cookie session."""
        return self._mgmt_request(
            method,
            path,
            payload=payload,
            session=session,
            csrf_token=csrf_token,
            extra_headers=headers,
        )

    def _mgmt_get(self, path, session=None, csrf_token=None):
        """GET a management API path with the given cookie session."""
        return self._mgmt_request(
            "GET", path, payload=None, session=session, csrf_token=csrf_token
        )

    # ------------------------------------------------------------------
    # Account actions
    # ------------------------------------------------------------------
    def action_test_connection(self):
        self.ensure_one()
        try:
            result = self._call("getMe") or {}
        except UniomAPIError as error:
            return self._notify_warning(self._friendly_gateway_error(error))
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
                self.env["ir.config_parameter"].sudo().get_str("web.base.url", "").rstrip("/")
            )
            if not base:
                raise UserError(
                    _("Set the 'web.base.url' system parameter to your Odoo base URL first.")
                )
            url = "%s/uniom/webhook/%s" % (base, connection.id)
            # Uniom refuses private hosts; validate on our side first so the
            # user gets an actionable message instead of a gateway 400.
            validate_public_http_url(url)
            try:
                connection._call(
                    "setWebhook",
                    {
                        "url": url,
                        "secret_token": connection.webhook_secret,
                        "allowed_updates": ["message", "edited_message", "channel_post"],
                        # NEVER drop the backlog on register: anything queued
                        # while polling (or while the webhook was down) must
                        # still be delivered afterwards.
                        "drop_pending_updates": False,
                    },
                )
            except UniomAPIError as error:
                return self._notify_warning(self._friendly_gateway_error(error))
            connection.write(
                {
                    "webhook_url": url,
                    "webhook_registered": True,
                    "inbound_mode": "webhook",
                }
            )
        return self._notify_success(_("Webhook registered."))

    def action_delete_webhook(self):
        for connection in self:
            try:
                connection._call("deleteWebhook", {"drop_pending_updates": False})
            except UniomAPIError as error:
                return self._notify_warning(self._friendly_gateway_error(error))
            connection.write({"webhook_url": False, "webhook_registered": False})
        return True

    def action_start_polling(self):
        """Cut this connection over to getUpdates polling.

        The webhook must be removed first, otherwise the gateway refuses
        every getUpdates call with a conflict. Pending updates are kept so
        nothing that arrived while the switch happens is lost.
        """
        for connection in self:
            try:
                connection._call("deleteWebhook", {"drop_pending_updates": False})
            except UniomAPIError as error:
                return self._notify_warning(self._friendly_gateway_error(error))
            connection.write(
                {
                    "inbound_mode": "polling",
                    "webhook_url": False,
                    "webhook_registered": False,
                    "last_poll_error": False,
                    "poll_backoff_until": False,
                }
            )
        return self._notify_success(
            _("Polling enabled: incoming updates are fetched by the cron.")
        )

    def action_stop_polling(self):
        """Switch back to webhook mode without touching the registration.

        The user presses Register Webhook when the instance is reachable.
        """
        self.write(
            {
                "inbound_mode": "webhook",
                "last_poll_error": False,
                "poll_backoff_until": False,
            }
        )
        return self._notify_success(
            _("Polling stopped. Register the webhook when your Odoo URL is reachable.")
        )

    def action_refresh_webhook_info(self):
        for connection in self:
            try:
                info = connection._call("getWebhookInfo") or {}
            except UniomAPIError as error:
                return self._notify_warning(self._friendly_gateway_error(error))
            url = info.get("url") or ""
            connection.write(
                {
                    "webhook_pending_count": int(info.get("pending_update_count") or 0),
                    "webhook_last_error": info.get("last_error_message") or False,
                    "webhook_registered": bool(url),
                    "webhook_url": url or False,
                }
            )
        return self._notify_success(_("Webhook status refreshed."))

    def action_sync_dialogs(self):
        """Seed the conversation list from the account's dialog list."""
        synced_at = fields.Datetime.now()
        total = 0
        for connection in self:
            try:
                dialogs = connection._call("getDialogs", {"limit": 100}) or []
            except UniomAPIError as error:
                return self._notify_warning(self._friendly_gateway_error(error))
            if not isinstance(dialogs, list):
                dialogs = []
            for item in dialogs:
                if isinstance(item, dict):
                    connection._upsert_dialog(item, synced_at)
                    total += 1
            connection.write({"last_dialog_sync_at": synced_at})
        return self._notify_success(_("%s conversations synchronized.", total))

    def _upsert_dialog(self, item, synced_at):
        """Insert or refresh the uniom.chat row described by one DialogItem."""
        self.ensure_one()
        raw_id = item.get("id")
        if raw_id is None:
            return self.env["uniom.chat"]
        chat_id = canonicalize_chat_id(str(raw_id)) or str(raw_id)
        chat_model = self.env["uniom.chat"]
        valid_types = dict(chat_model._fields["chat_type"].selection)
        chat_type = item.get("type") if item.get("type") in valid_types else "unknown"
        full_name = " ".join(
            part for part in (item.get("first_name"), item.get("last_name")) if part
        )
        values = {
            "messenger_title": item.get("title") or full_name or item.get("username") or chat_id,
            "chat_type": chat_type,
            "messenger_username": item.get("username") or False,
            "messenger_photo_url": item.get("photo_url") or "",
        }
        chat = chat_model.search(
            [("connection_id", "=", self.id), ("chat_id", "=", chat_id)], limit=1
        )
        if not chat or not chat.partner_id:
            # dialogs carry no phone: match explicit chat ids and @usernames
            # only, never create — creation stays with real inbound traffic
            partner = self._match_partner_for_dialog(chat_id, item.get("username"))
            if partner:
                values["partner_id"] = partner.id
        if chat:
            chat.write(values)
            return chat
        values.update(
            {
                "connection_id": self.id,
                "chat_id": chat_id,
                "company_id": (self.company_id or self.env.company).id,
            }
        )
        try:
            # unique(connection_id, chat_id): the dialog sync can race the
            # webhook creating the same conversation
            with self.env.cr.savepoint():
                return chat_model.create(values)
        except IntegrityError:
            chat = chat_model.search(
                [("connection_id", "=", self.id), ("chat_id", "=", chat_id)], limit=1
            )
            if chat:
                chat.write(values)
            return chat

    def _match_partner_for_dialog(self, chat_id, username):
        """Match an existing contact for a dialog row. Read-only: dialogs
        carry display names, not verified phones, so this never creates."""
        partner = self.env["res.partner"]
        if chat_id:
            explicit = partner.search([("uniom_chat_id", "=", chat_id)], limit=1)
            if explicit:
                return explicit
            if chat_id.startswith("+"):
                phone_like = partner.search(
                    [("phone", "=", chat_id)], limit=1
                )
                if phone_like:
                    return phone_like
        if username:
            handle = "@" + str(username).lstrip("@")
            named = partner.search([("uniom_chat_id", "=", handle)], limit=1)
            if named:
                return named
        return partner

    def _notify_success(self, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Uniom"), "message": message, "type": "success", "sticky": False},
        }

    def _notify_warning(self, message, title=None):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title or _("Uniom"),
                "message": message,
                "type": "warning",
                "sticky": True,
            },
        }

    @api.model
    def _friendly_gateway_error(self, error):
        """Map a UniomAPIError to a one-line actionable message.

        Buttons must never surface raw tracebacks: 401/403 mean the key is
        dead, 429 means slow down, 5xx/network mean try later.
        """
        code = getattr(error, "error_code", None)
        if code in (401, 403):
            return _(
                "The API key was rejected (revoked or wrong account). "
                "Create a fresh key in your Uniom dashboard and update it here."
            )
        if code == 429:
            retry = getattr(error, "retry_after", None)
            if retry:
                return _("Too many requests — try again in %s seconds.", retry)
            return _("Too many requests — wait a minute and try again.")
        if code is not None and 500 <= code < 600:
            return _(
                "The Uniom gateway is having trouble (HTTP %s). "
                "Try again in a few minutes.", code,
            )
        text = str(error.args[0]) if error.args else str(error)
        # _call prefixes transport failures; keep them short for toasts
        return text[:300] if text else _("The Uniom gateway did not answer.")

    def _friendly_call(self, method, *args, **kwargs):
        """Call a button-style action; return None or human-readable error.

        Actions signal gateway failures either by raising (UserError
        family, incl. ValidationError) or by returning a warning
        notification — normalize both so wizard fallbacks actually
        trigger instead of silently assuming success. Never raises:
        wizard follow-up steps are best effort.
        """
        self.ensure_one()
        try:
            # isolate DB errors: without a savepoint a failed write aborts
            # the whole transaction and the wizard's next write dies with
            # InFailedSqlTransaction instead of a best-effort note
            with self.env.cr.savepoint():
                result = getattr(self, method)(*args, **kwargs)
        except UserError as error:
            return str(error.args[0]) if error.args else str(error)
        except Exception:  # noqa: BLE001 - wizard steps must never traceback
            _logger.exception("Uniom: %s failed unexpectedly", method)
            return _("The action failed unexpectedly; retry it from the connection form.")
        if isinstance(result, dict):
            params = result.get("params") or {}
            if params.get("type") == "warning":
                return params.get("message") or _("The action did not complete.")
        return None

    # ------------------------------------------------------------------
    # Inbound updates (webhook controller and getUpdates polling)
    # ------------------------------------------------------------------
    def _process_inbound_update(self, update):
        """Store one Telegram-shaped update; shared by webhook and polling.

        Returns True when a message row was created or updated. Media
        downloads and bus/chatter side effects are best effort: losing a
        preview or a bus ping must never lose the message itself.
        """
        self.ensure_one()
        if not isinstance(update, dict):
            return False
        self.write({"last_webhook_at": fields.Datetime.now()})

        update_key = self._update_key(update)
        if update_key and self.env["uniom.message"].search_count(
            [("connection_id", "=", self.id), ("uniom_update_id", "=", update_key)], limit=1
        ):
            # webhook retry or the polling cron replaying an acknowledged page
            return False

        edited, message = self._extract_update_message(update)
        if not message:
            return False
        chat = message.get("chat") or {}
        # canonicalize so inbound and reply paths converge on one thread key
        raw_chat_id = str(chat.get("id") or "")
        chat_id = canonicalize_chat_id(raw_chat_id) or raw_chat_id
        if not chat_id:
            return False
        message_id = message.get("message_id")
        message_key = str(message_id) if message_id is not None else False
        kind = self._detect_message_kind(message)
        body = self._compose_message_body(message, kind)
        sender = message.get("from") or {}

        if edited and message_key:
            existing = self.env["uniom.message"].search(
                [
                    ("connection_id", "=", self.id),
                    ("chat_id", "=", chat_id),
                    ("uniom_message_id", "=", message_key),
                ],
                limit=1,
            )
            if existing:
                existing.write(
                    {
                        "body": body,
                        "message_kind": kind,
                        "date_edited": fields.Datetime.now(),
                        "edit_count": existing.edit_count + 1,
                        "uniom_update_id": update_key or existing.uniom_update_id,
                    }
                )
                if existing.chat_session_id:
                    existing.chat_session_id._touch_from(existing)
                return True

        if not edited and message_key:
            # the dashboard may already have backfilled this message via
            # getChatHistory; polling/webhook delivery must not duplicate it
            existing = self.env["uniom.message"].search(
                [
                    ("connection_id", "=", self.id),
                    ("chat_id", "=", chat_id),
                    ("uniom_message_id", "=", message_key),
                ],
                limit=1,
            )
            if existing:
                if update_key and existing.uniom_update_id != update_key:
                    existing.uniom_update_id = update_key
                return False
        partner = self._find_partner_for_chat(chat_id, sender, chat)
        if not partner:
            return False
        values = {
            "connection_id": self.id,
            "direction": self._direction_for_sender(message),
            "state": "sent",
            "chat_id": chat_id,
            "partner_id": partner.id,
            "body": body,
            "message_kind": kind,
            "uniom_message_id": message_key,
            "uniom_update_id": update_key,
            "date_sent": _datetime_from_timestamp(message.get("date"))
            or fields.Datetime.now(),
            # anchor inbound records to the connection's company (not the
            # superuser default) so multi-company users see their threads
            "company_id": (self.company_id or partner.company_id).id,
            "record_res_model": "res.partner",
            "record_res_id": partner.id,
            "record_name": partner.display_name,
        }
        try:
            with self.env.cr.savepoint():
                message_record = self.env["uniom.message"].create(values)
        except IntegrityError:
            # the polling cron and a webhook replay raced past the pre-check
            return False

        try:
            descriptor = self._get_media_descriptor(message, kind)
            if descriptor:
                self._download_inbound_media(message_record, descriptor)
        except Exception:  # noqa: BLE001 - a file must never lose the message
            _logger.warning(
                "Uniom: could not download media for message %s",
                message_record.id,
                exc_info=True,
            )

        if message_record.direction == "in" and hasattr(partner, "message_post"):
            try:
                partner.message_post(
                    body=self._inbound_chatter_body(
                        body, kind, message_record.chat_session_id
                    ),
                    author_id=partner.id,
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                )
            except Exception:  # noqa: BLE001 - chatter must never lose the message
                _logger.warning(
                    "Uniom: could not post chatter for message %s",
                    message_record.id,
                    exc_info=True,
                )
        return True

    def _update_key(self, update):
        update_id = update.get("update_id")
        return str(update_id) if update_id is not None else False

    def _extract_update_message(self, update):
        for key in UPDATE_MESSAGE_KEYS:
            message = update.get(key)
            if isinstance(message, dict):
                return key.startswith("edited_"), message
        return False, None

    def _detect_message_kind(self, message):
        """Map a Telegram-shaped Message payload to our message_kind."""
        if message.get("photo"):
            return "photo"
        if message.get("document"):
            return "document"
        if message.get("video") or message.get("video_note") or message.get("animation"):
            return "video"
        if message.get("audio"):
            return "audio"
        if message.get("voice"):
            return "voice"
        if message.get("sticker"):
            return "sticker"
        if message.get("location"):
            return "location"
        if message.get("contact"):
            return "contact"
        if message.get("poll"):
            return "poll"
        if message.get("text") is not None or message.get("caption") is not None:
            return "text"
        return "unknown"

    def _compose_message_body(self, message, kind):
        """Text/caption, or a readable label for media-only payloads."""
        text = (message.get("text") or message.get("caption") or "").strip()
        if text:
            # messengers cap texts around 4096 chars; keep hostile overlong
            # payloads from flooding the log and the chatter
            return text[:4096]
        if kind == "photo":
            label = _("Photo")
        elif kind == "document":
            document = message.get("document") or {}
            label = _("Document: %(name)s", name=document.get("file_name") or _("file"))
        elif kind == "video":
            label = _("Video")
        elif kind == "audio":
            audio = message.get("audio") or {}
            title = audio.get("title") or audio.get("performer")
            label = _("Audio: %(name)s", name=title) if title else _("Audio")
        elif kind == "voice":
            label = _("Voice message")
        elif kind == "sticker":
            label = _("Sticker")
        elif kind == "location":
            location = message.get("location") or {}
            label = _(
                "Location: %(lat)s, %(lon)s",
                lat=location.get("latitude"),
                lon=location.get("longitude"),
            )
        elif kind == "contact":
            contact = message.get("contact") or {}
            full_name = " ".join(
                part
                for part in (contact.get("first_name"), contact.get("last_name"))
                if part
            )
            label = _(
                "Contact: %(name)s %(phone)s",
                name=full_name or _("contact"),
                phone=contact.get("phone_number") or "",
            )
        elif kind == "poll":
            poll = message.get("poll") or {}
            label = _("Poll: %(question)s", question=poll.get("question") or _("poll"))
        else:
            label = _("Unsupported message")
        return label[:4096]

    def _get_media_descriptor(self, message, kind):
        """Pick the downloadable file carried by a media message."""
        if kind == "photo":
            photos = message.get("photo") or []
            if photos:
                # Telegram lists sizes ascending; max() also copes with
                # gateways that do not guarantee the order.
                best = max(
                    photos,
                    key=lambda item: (
                        item.get("file_size") or 0,
                        (item.get("width") or 0) * (item.get("height") or 0),
                    ),
                )
                return {
                    "file_id": best.get("file_id"),
                    "file_size": best.get("file_size"),
                    "name": "photo-%s.jpg" % (message.get("message_id") or "file"),
                    "mimetype": "image/jpeg",
                }
        elif kind == "document":
            document = message.get("document") or {}
            return {
                "file_id": document.get("file_id"),
                "file_size": document.get("file_size"),
                "name": document.get("file_name") or "document",
                "mimetype": document.get("mime_type") or "application/octet-stream",
            }
        elif kind == "video":
            video = (
                message.get("video")
                or message.get("video_note")
                or message.get("animation")
                or {}
            )
            return {
                "file_id": video.get("file_id"),
                "file_size": video.get("file_size"),
                "name": video.get("file_name") or "video.mp4",
                "mimetype": video.get("mime_type") or "video/mp4",
            }
        elif kind == "audio":
            audio = message.get("audio") or {}
            return {
                "file_id": audio.get("file_id"),
                "file_size": audio.get("file_size"),
                "name": "audio.mp3",
                "mimetype": audio.get("mime_type") or "audio/mpeg",
            }
        elif kind == "voice":
            voice = message.get("voice") or {}
            return {
                "file_id": voice.get("file_id"),
                "file_size": voice.get("file_size"),
                "name": "voice.ogg",
                "mimetype": voice.get("mime_type") or "audio/ogg",
            }
        elif kind == "sticker":
            sticker = message.get("sticker") or {}
            return {
                "file_id": sticker.get("file_id"),
                "file_size": sticker.get("file_size"),
                "name": "sticker.webp",
                "mimetype": sticker.get("mime_type") or "image/webp",
            }
        return None

    def _download_file_bytes(self, file_id):
        """getFile + stream the bytes, returning them (profile photos)."""
        self.ensure_one()
        if not file_id:
            return False
        file_info = self._call("getFile", {"file_id": file_id}) or {}
        file_path = file_info.get("file_path")
        if not file_path:
            return False
        base = (self.base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        url = "%s/file/bot%s/%s" % (base, self.api_key, str(file_path).lstrip("/"))
        try:
            validate_public_http_url(url)
        except ValidationError as error:
            raise ValidationError(self._safe_error(error)) from error
        try:
            response = requests.get(
                url, stream=True, timeout=REQUEST_TIMEOUT, allow_redirects=False
            )
        except requests.RequestException as error:
            raise UniomAPIError(
                _("Network error while downloading a file: %s", self._safe_error(error)),
                transient=True,
            ) from error
        with response:
            if response.status_code != 200:
                raise UniomAPIError(
                    _("File download failed (HTTP %s).", response.status_code),
                    error_code=response.status_code,
                )
            chunks = []
            total = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_MEDIA_BYTES:
                    raise UniomAPIError(self._too_large_message())
                chunks.append(chunk)
            return b"".join(chunks)

    def _download_inbound_media(self, message_record, descriptor):
        """getFile + stream the bytes into an ir.attachment.

        The download URL is built from our own validated gateway base, so it
        is same-host by construction; it is re-validated before the request.
        """
        self.ensure_one()
        file_id = descriptor.get("file_id")
        if not file_id:
            return False
        file_info = self._call("getFile", {"file_id": file_id}) or {}
        file_path = file_info.get("file_path")
        if not file_path:
            return False
        base = (self.base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        url = "%s/file/bot%s/%s" % (base, self.api_key, str(file_path).lstrip("/"))
        try:
            validate_public_http_url(url)
        except ValidationError as error:
            raise ValidationError(self._safe_error(error)) from error
        try:
            response = requests.get(
                url, stream=True, timeout=REQUEST_TIMEOUT, allow_redirects=False
            )
        except requests.RequestException as error:
            raise UniomAPIError(
                _("Network error while downloading a file: %s", self._safe_error(error)),
                transient=True,
            ) from error
        with response:
            if response.status_code != 200:
                raise UniomAPIError(
                    _("File download failed (HTTP %s).", response.status_code),
                    error_code=response.status_code,
                )
            declared_size = file_info.get("file_size") or descriptor.get("file_size")
            if declared_size and int(declared_size) > MAX_MEDIA_BYTES:
                raise UniomAPIError(self._too_large_message())
            chunks = []
            total = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_MEDIA_BYTES:
                    raise UniomAPIError(self._too_large_message())
                chunks.append(chunk)
            content = b"".join(chunks)
            header_type = (response.headers.get("Content-Type") or "").split(";")[0].strip()
        if header_type and "/" not in header_type:
            # some platform adapters answer with a bare extension ("png")
            header_type = mimetypes.guess_type("file." + header_type.lower())[0] or ""
        mimetype = header_type or descriptor.get("mimetype") or "application/octet-stream"
        self.env["ir.attachment"].sudo().create(
            {
                "name": descriptor.get("name") or "file",
                "raw": content,
                "mimetype": mimetype,
                "res_model": "uniom.message",
                "res_id": message_record.id,
            }
        )
        return True

    def _too_large_message(self):
        return _(
            "File is larger than the %(mb)s MB limit.",
            mb=MAX_MEDIA_BYTES // (1024 * 1024),
        )

    def _kind_label(self, kind):
        selection = self.env["uniom.message"]._fields["message_kind"].selection
        return dict(selection).get(kind, kind)

    def _inbound_chatter_body(self, body, kind, chat):
        base_url = (
            self.env["ir.config_parameter"].sudo().get_str("web.base.url", "").rstrip("/")
        )
        deep_link = (
            "%s/web#action=uniom_connector.action_uniom_chat_dashboard&uniom_chat_id=%s"
            % (base_url, chat.id)
        )
        # Markup (not str): message_post escapes plain str, which would show
        # literal <p> tags; every interpolated part is escaped above
        return Markup(
            '<p>%s</p><p>%s</p><p><a href="%s">%s</a></p>'
            % (
                html_escape(_("Incoming %(kind)s message", kind=self._kind_label(kind))),
                html_escape(body or ""),
                html_escape(deep_link),
                html_escape(_("Open in Uniom Conversations")),
            )
        )

    # ------------------------------------------------------------------
    # getUpdates polling
    # ------------------------------------------------------------------
    def _poll_once(self):
        """Fetch and store one getUpdates page; safe to call from the cron."""
        self.ensure_one()
        if self.inbound_mode != "polling":
            return 0
        now = fields.Datetime.now()
        if self.poll_backoff_until and self.poll_backoff_until > now:
            return 0
        payload = {"timeout": 0, "limit": POLL_LIMIT}
        if self.poll_offset:
            try:
                payload["offset"] = int(self.poll_offset)
            except (TypeError, ValueError):
                # a corrupted offset must not stop polling forever: the next
                # successful page rewrites it with max(update_id) + 1
                pass
        try:
            allowed_updates = json.loads(self.poll_allowed_updates or "[]")
        except (TypeError, ValueError):
            allowed_updates = []
        if isinstance(allowed_updates, list) and allowed_updates:
            payload["allowed_updates"] = allowed_updates
        try:
            updates = self._call("getUpdates", payload) or []
        except UniomAPIError as error:
            text = self._safe_error(error)
            values = {"last_poll_error": text}
            if error.error_code == 409 or "conflict" in text.lower():
                # a webhook is still registered: retry later, not every minute
                values["poll_backoff_until"] = fields.Datetime.add(
                    now, minutes=POLL_CONFLICT_BACKOFF_MINUTES
                )
            self.write(values)
            _logger.warning("Uniom polling failed for %s: %s", self.name, text)
            return 0

        if not isinstance(updates, list):
            updates = []
        max_update_id = None
        failed_ids = []
        for update in updates:
            if not isinstance(update, dict):
                continue
            update_id = update.get("update_id")
            try:
                numeric_id = int(update_id)
            except (TypeError, ValueError):
                numeric_id = None
            if numeric_id is not None and (max_update_id is None or numeric_id > max_update_id):
                max_update_id = numeric_id
            try:
                # one poison update must not block the rest of the page and
                # must not abort the whole cron transaction
                with self.env.cr.savepoint():
                    self._process_inbound_update(update)
            except Exception:  # noqa: BLE001 - keep polling the page
                _logger.exception("Uniom: could not process update %s", update_id)
                if numeric_id is not None:
                    failed_ids.append(numeric_id)
        values = {
            "last_poll_at": fields.Datetime.now(),
            "last_poll_error": False,
            "poll_backoff_until": False,
        }
        if max_update_id is not None:
            if failed_ids:
                first_failed = str(min(failed_ids))
                if first_failed == (self.poll_failed_update_id or ""):
                    streak = (self.poll_failed_streak or 0) + 1
                else:
                    streak = 1
                values["poll_failed_update_id"] = first_failed
                values["poll_failed_streak"] = streak
                if streak > MAX_POLL_FAILED_STREAK:
                    # permanently poison: holding the offset would wedge
                    # polling (the gateway page limit hides newer updates),
                    # so skip it loudly instead of retrying forever. The raw
                    # payload is kept as a dead letter for support replay.
                    dead = next(
                        (
                            u for u in updates
                            if isinstance(u, dict)
                            and str(u.get("update_id")) == first_failed
                        ),
                        None,
                    )
                    _logger.error(
                        "Uniom: dropping poison update %s after %s failed polls",
                        first_failed, streak,
                    )
                    values["poll_offset"] = str(max_update_id + 1)
                    values["last_poll_error"] = _(
                        "Update %s failed %s times and was skipped; "
                        "payload kept on the connection.", first_failed, streak,
                    )
                    values["poll_failed_update_id"] = False
                    values["poll_failed_streak"] = 0
                    values["poll_dead_update"] = json.dumps(
                        {
                            "skipped_at": fields.Datetime.now().isoformat(),
                            "update": dead,
                        },
                        default=str,
                    )[:10000]
                else:
                    # a transient failure (DB/deadlock, chatter error) must
                    # not lose the message: redeliver from the first failed
                    # update; successes later in the page dedupe by update id
                    values["poll_offset"] = first_failed
                    values["last_poll_error"] = _(
                        "%s update(s) failed processing and will be retried.", len(failed_ids)
                    )
            else:
                # acknowledging the page: the gateway drops everything below this
                values["poll_offset"] = str(max_update_id + 1)
                values["poll_failed_update_id"] = False
                values["poll_failed_streak"] = 0
        self.write(values)
        return len(updates)

    @api.model
    def _cron_poll_updates(self):
        connections = self.search([("active", "=", True), ("inbound_mode", "=", "polling")])
        for connection in connections:
            try:
                with self.env.cr.savepoint():
                    connection._poll_once()
            except Exception:  # noqa: BLE001 - never raise out of the cron
                _logger.exception(
                    "Uniom polling cron failed for connection %s", connection.id
                )
        return True

    @api.model
    def _cron_sync_presence(self):
        """Refresh last-seen for the 20 most stale recent private chats."""
        now = fields.Datetime.now()
        domain = [
            ("connection_id.active", "=", True),
            ("chat_type", "=", "private"),
            ("last_message_date", ">=", fields.Datetime.subtract(now, days=30)),
            "|",
            ("presence_updated_at", "=", False),
            ("presence_updated_at", "<", fields.Datetime.subtract(now, hours=6)),
        ]
        chats = self.env["uniom.chat"].search(
            domain,
            limit=20,
            order="presence_updated_at asc nulls first, id asc",
        )
        for chat in chats:
            try:
                with self.env.cr.savepoint():
                    chat.action_sync_presence()
            except Exception:  # noqa: BLE001 - never raise out of the cron
                _logger.exception("Uniom presence sync failed for chat %s", chat.id)
        return True

    # ------------------------------------------------------------------
    # Account helpers
    # ------------------------------------------------------------------
    def _own_user_id(self):
        """The account's own messenger user id, from the cached getMe JSON."""
        self.ensure_one()
        try:
            details = json.loads(self.account_details or "{}")
        except (TypeError, ValueError):
            return False
        if not isinstance(details, dict):
            return False
        own_id = details.get("id")
        return str(own_id) if own_id is not None else False

    def _direction_for_sender(self, message):
        """in/out for one Telegram-shaped message by its author.

        Compares every author-carrying field (`from`, `sender_chat`,
        `forward_from`, `via_bot`) against the cached own id, coercing
        both sides to text: gateway ids arrive as int, str, or numeric
        strings depending on platform and route. Unknown author → "in"
        (safer: badges and chatter fire rather than silently dropping).
        """
        self.ensure_one()
        own_id = self._own_user_id()
        if not own_id or not isinstance(message, dict):
            return "in"
        candidates = []
        for key in ("from", "sender_chat", "forward_from", "via_bot"):
            author = message.get(key)
            if isinstance(author, dict) and author.get("id") is not None:
                candidates.append(str(author["id"]))
        if not candidates:
            return "in"
        return "out" if own_id in candidates else "in"

    def _find_partner_for_chat(self, chat_id, sender, chat):
        partner = self.env["res.partner"]
        if chat_id:
            explicit = partner.search([("uniom_chat_id", "=", chat_id)], limit=1)
            if explicit:
                return explicit
            if chat_id.startswith("+"):
                phone_like = partner.search(
                    [("phone", "=", chat_id)], limit=1
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
            values["phone"] = chat_id
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
