# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Link a messenger account to Uniom from inside Odoo.

The wizard mirrors the Uniom panel's connect-account flow: sign in to the
management API with a phone number and one-time code, link a messenger
credential (``/platforms/<name>/link/start`` + ``/link/verify``, or
``/link/bot``), then mint an API key for that credential and save it on a
regular :class:`~odoo.addons.uniom_connector.models.uniom_connection`.

Authentication is cookie based, exactly like the panel: every button press
builds a :class:`requests.Session`, the gateway's HttpOnly ``access_token``
and ``otp_client_id`` cookies live in that session, and the cookie jar is
serialized into the transient ``mgmt_cookies`` field so the next press can
restore it. The CSRF token returned by ``/auth/login`` is kept in
``mgmt_csrf`` and sent as ``X-CSRF-Token`` on non-GET management calls.

The management cookies, CSRF token, passwords, OTPs and bot tokens live only
on this transient wizard; they are never written to ``uniom.connection`` and
never logged.
"""

import json
import logging
import re
from urllib.parse import quote

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.uniom_tools import DEFAULT_BASE_URL

_logger = logging.getLogger(__name__)

# Messengers this wizard can link (the step-2 phone/OTP flow and the bot-token
# alternative both exist for these names in the management API).
LINK_PLATFORMS = [
    ("bale", "Bale"),
    ("rubika", "Rubika"),
    ("eitaa", "Eitaa"),
    ("soroushplus", "Soroush+"),
    ("telegram", "Telegram"),
]
_PLATFORM_LABELS = dict(LINK_PLATFORMS)

_PHONE_RE = re.compile(r"^\+?\d{7,15}$")
_OTP_RE = re.compile(r"^\d{4,8}$")

# Persian and Arabic digits are common in phone numbers pasted from local
# apps; normalize them before validating.
_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


def _translate_digits(value):
    return (value or "").translate(_DIGIT_TRANSLATION)


def _normalize_phone(value):
    """Return an E.164-style phone number, accepting local Iranian numbers."""
    phone = re.sub(r"[\s\-()]", "", _translate_digits(str(value or "")).strip())
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if not _PHONE_RE.match(phone):
        raise UserError(
            _(
                "Enter a valid phone number in international format, for "
                "example +989123456789."
            )
        )
    if not phone.startswith("+") and phone.startswith("0"):
        phone = "+98" + phone[1:]
    return phone


def _normalize_otp(value):
    otp = _translate_digits(str(value or "")).strip()
    if not _OTP_RE.match(otp):
        raise UserError(_("Enter the 4 to 8 digit verification code."))
    return otp


class UniomLinkWizard(models.TransientModel):
    _name = "uniom.link.wizard"
    _description = "Link Messenger Account"

    # The contract's five coarse states. The messenger-linking screens are
    # distinguished by mgmt_signed_in (signed in or not) and link_session_id
    # (phone form or OTP form), so no secret is needed to tell them apart.
    step = fields.Selection(
        [
            ("draft", "Sign In"),
            ("otp", "Verification"),
            ("password", "Two-Step Password"),
            ("bot_token", "Bot Token"),
            ("done", "Done"),
        ],
        default="draft",
        required=True,
        copy=False,
    )

    # Transient management state. NEVER copied to uniom.connection.
    mgmt_cookies = fields.Text(
        readonly=True,
        copy=False,
        help="Serialized requests.Session cookie jar (HttpOnly gateway "
        "cookies included). Transient only: never copied to a connection.",
    )
    mgmt_csrf = fields.Char(readonly=True, copy=False)
    mgmt_signed_in = fields.Boolean(readonly=True, copy=False, default=False)
    otp_client_id = fields.Char(readonly=True, copy=False)

    base_url = fields.Char(
        string="Gateway URL",
        default=lambda self: self.env["ir.config_parameter"].sudo().get_param(
            "uniom_connector.default_base_url", DEFAULT_BASE_URL
        ),
        required=True,
        readonly=True,
        help="Set once in Settings → Uniom → Gateway URL; every wizard "
        "and connection uses that value.",
    )

    # Step 1/2: Uniom account sign-in.
    uniom_phone = fields.Char(string="Uniom Phone")
    uniom_otp = fields.Char(string="Verification Code", copy=False)

    # Step 3+: messenger credential linking.
    # link_platform stays a static selection for form stability, but its
    # value always comes from the live GET /platforms list stored in
    # available_platforms (JSON: [{name, display_name, auth_types[]}]);
    # the brand strip + validation below both read that list, exactly
    # like the Uniom panel renders platforms from the same endpoint.
    link_platform = fields.Selection(LINK_PLATFORMS, string="Messenger")
    available_platforms = fields.Text(readonly=True, copy=False)
    link_phone = fields.Char(string="Messenger Phone")
    link_auth_type = fields.Selection(
        selection="_selection_link_auth_type",
        string="Login Method",
        help="Login methods offered by the gateway for this platform.",
    )
    link_auth_options = fields.Text(
        readonly=True, copy=False,
        help="JSON list of {type, name, description} for the chosen "
        "platform, from GET /platforms — drives the radio cards.",
    )
    link_dynamic_token = fields.Char(string="Token", copy=False)
    link_dynamic_token_label = fields.Char(readonly=True, copy=False)
    link_dynamic_token_placeholder = fields.Char(readonly=True, copy=False)
    link_dynamic_help = fields.Char(readonly=True, copy=False)
    link_pair_code = fields.Char(readonly=True, copy=False)
    link_qr_link = fields.Char(readonly=True, copy=False)
    link_session_id = fields.Char(readonly=True, copy=False)
    verification_mode = fields.Char(readonly=True, copy=False)
    link_otp = fields.Char(string="Verification Code", copy=False)
    link_password = fields.Char(string="Two-Step Password", copy=False)
    link_bot_token = fields.Char(string="Bot Token", copy=False)
    link_credential_id = fields.Integer(readonly=True, copy=False)
    link_phone_display = fields.Char(readonly=True, copy=False)
    link_message = fields.Char(readonly=True, copy=False)

    # Final step: API key + Odoo connection.
    api_key_name = fields.Char(string="API Key Name", default="Odoo", required=True)
    inbound_mode = fields.Selection(
        [("webhook", "Webhook (instant)"), ("polling", "Polling (works everywhere)")],
        string="Receive Messages Via",
        default="polling",
        required=True,
    )
    created_connection_id = fields.Many2one(
        "uniom.connection", readonly=True, copy=False
    )

    # ------------------------------------------------------------------
    # Cookie session plumbing
    # ------------------------------------------------------------------
    def _management_session(self):
        """Rebuild the cookie session saved on this wizard."""
        session = requests.Session()
        try:
            stored = json.loads(self.mgmt_cookies or "[]")
        except (TypeError, ValueError):
            stored = []
        if isinstance(stored, dict):
            stored = [
                {"name": name, "value": value} for name, value in stored.items()
            ]
        elif not isinstance(stored, list):
            stored = []
        for item in stored:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            cookie_kwargs = {"path": item.get("path") or "/"}
            if item.get("domain"):
                cookie_kwargs["domain"] = item["domain"]
            if item.get("secure"):
                cookie_kwargs["secure"] = True
            if item.get("expires") is not None:
                cookie_kwargs["expires"] = item["expires"]
            session.cookies.set(
                item["name"], item.get("value") or "", **cookie_kwargs
            )
        return session

    @staticmethod
    def _dump_cookies(session):
        """Serialize the session cookie jar into the transient field."""
        return json.dumps(
            [
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain or "",
                    "path": cookie.path or "/",
                    "secure": bool(cookie.secure),
                    "expires": cookie.expires,
                }
                for cookie in session.cookies
            ]
        )

    def _save_cookies(self, session):
        self.mgmt_cookies = self._dump_cookies(session)

    def _mgmt_post(
        self, path, payload=None, session=None, csrf_token=None, headers=None
    ):
        """Call a management POST through an unsaved connection record.

        The helper lives on ``uniom.connection`` (it needs the gateway URL),
        but no connection is created until the final step. The caller's
        session keeps the gateway cookies; the CSRF token is only attached
        by the helper on non-GET methods.
        """
        connection = self.env["uniom.connection"].new({"base_url": self.base_url})
        return connection._mgmt_call(
            path, payload, session=session, csrf_token=csrf_token, headers=headers
        )

    def _mgmt_get(self, path, session=None, csrf_token=None):
        connection = self.env["uniom.connection"].new({"base_url": self.base_url})
        return connection._mgmt_get(
            path, session=session, csrf_token=csrf_token
        )

    def _reopen_wizard(self):
        """Re-open this same transient record after a step transition.

        A type=object button returning nothing is converted by the web client
        into ``ir.actions.act_window_close``, which would close the dialog.
        Returning the same record keeps the multi-step form open and reloads
        it with the fields written by the action.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Link Messenger Account"),
            "res_model": "uniom.link.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": dict(self.env.context, edit=True),
        }

    # ------------------------------------------------------------------
    # Step 1/2: sign in to Uniom
    # ------------------------------------------------------------------
    def action_send_otp(self):
        """Send (or resend) the Uniom sign-in code to ``uniom_phone``."""
        self.ensure_one()
        if self.mgmt_signed_in:
            raise UserError(_("You are already signed in to Uniom."))
        phone = _normalize_phone(self.uniom_phone)
        session = self._management_session()
        headers = None
        if self.otp_client_id:
            headers = {"X-Uniom-Otp-Client-Id": self.otp_client_id}
        response = (
            self._mgmt_post(
                "/auth/sendOtp", {"phone": phone}, session=session, headers=headers
            )
            or {}
        )
        if not response.get("success", True):
            raise UserError(
                _(
                    "Uniom could not send the verification code: %s",
                    response.get("message") or _("unknown error"),
                )
            )
        self.write(
            {
                "uniom_phone": phone,
                "uniom_otp": False,
                "otp_client_id": response.get("client_id") or self.otp_client_id,
                "mgmt_cookies": self._dump_cookies(session),
                "mgmt_csrf": False,
                "step": "otp",
                "link_message": response.get("message") or False,
            }
        )
        return self._reopen_wizard()

    def action_resend_otp(self):
        self.ensure_one()
        if self.step != "otp" or self.link_session_id:
            raise UserError(_("There is no Uniom sign-in code to resend."))
        return self.action_send_otp()

    def action_login(self):
        """Verify the Uniom OTP, keep the cookie session, load platforms."""
        self.ensure_one()
        phone = _normalize_phone(self.uniom_phone)
        otp = _normalize_otp(self.uniom_otp)
        session = self._management_session()
        headers = None
        if self.otp_client_id:
            headers = {"X-Uniom-Otp-Client-Id": self.otp_client_id}
        response = (
            self._mgmt_post(
                "/auth/login",
                {"phone": phone, "otp": otp},
                session=session,
                headers=headers,
            )
            or {}
        )
        # The gateway delivers the JWT as an HttpOnly cookie; the body's
        # csrf_token mirrors the csrf cookie and drives later POSTs.
        if not session.cookies.get("access_token"):
            raise UserError(
                _(
                    "Uniom signed you in but did not set an access-token "
                    "cookie. Check that the gateway allows cookie sessions "
                    "and try again."
                )
            )
        csrf_token = (
            response.get("csrf_token")
            or session.cookies.get("csrf_token")
            or ""
        ).strip()
        platforms = self._fetch_platforms(session, csrf_token)
        if not platforms:
            raise UserError(
                _(
                    "Uniom did not report a messenger account this wizard can "
                    "link. Enable Bale, Rubika, Eitaa, Soroush+ or Telegram on "
                    "the gateway and try again."
                )
            )
        link_platform = self.link_platform
        if link_platform not in platforms:
            link_platform = next(iter(platforms))
        stored = [
            {
                "name": name,
                "display_name": entry.get("display_name") or name,
                "auth_types": [
                    {
                        "type": at.get("type"),
                        "name": at.get("name") or at.get("type"),
                        "description": at.get("description") or "",
                        "requires_phone": bool(at.get("requires_phone")),
                        "requires_bot_token": bool(at.get("requires_bot_token")),
                        "is_oauth": bool(at.get("is_oauth")),
                        "is_redirect": bool(at.get("is_redirect")),
                        "input_type": at.get("input_type") or "",
                        "input_label": at.get("input_label") or "",
                        "input_placeholder": at.get("input_placeholder") or "",
                        "help_text": at.get("help_text") or "",
                        "button_text": at.get("button_text") or "",
                        "api_endpoint": at.get("api_endpoint") or "",
                        "platform_name": at.get("platform_name") or name,
                    }
                    for at in (entry.get("auth_types") or [])
                    if isinstance(at, dict) and at.get("enabled", True)
                ],
                "default_auth_type": entry.get("default_auth_type") or "",
            }
            for name, entry in platforms.items()
        ]
        auth_options, default_auth = self._auth_options_for(link_platform, stored)
        self.write(
            {
                "uniom_phone": phone,
                "uniom_otp": False,
                "otp_client_id": False,
                "mgmt_cookies": self._dump_cookies(session),
                "mgmt_csrf": csrf_token or False,
                "mgmt_signed_in": True,
                "step": "draft",
                "link_platform": link_platform,
                "available_platforms": json.dumps(stored),
                "link_auth_type": default_auth,
                "link_auth_options": json.dumps(auth_options),
                "link_session_id": False,
                "verification_mode": False,
                "link_otp": False,
                "link_password": False,
                "link_bot_token": False,
                "link_credential_id": False,
                "link_phone_display": False,
                "link_message": _("Signed in. Choose the messenger account to link."),
            }
        )
        return self._reopen_wizard()

    @api.model
    def _selection_link_auth_type(self):
        # static superset for form stability; the live per-platform list
        # lives in link_auth_options and _onchange_link_platform narrows
        # the value to it. Covers every v2 auth type seen in the wild.
        return [
            ("otp", "Phone Code"),
            ("standard", "Phone Code"),
            ("password", "Password"),
            ("bot_api", "Bot Token"),
            ("personal_token", "Personal Token"),
            ("client_credentials", "Client Credentials"),
            ("oauth_code", "OAuth Login"),
        ]

    @api.model
    def _auth_options_for(self, platform, stored):
        """(options, default) auth types for one platform, v2 rules."""
        entry = next((p for p in stored if p.get("name") == platform), {})
        options = entry.get("auth_types") or []
        default = entry.get("default_auth_type") or ""
        if default not in [o.get("type") for o in options]:
            default = options[0].get("type") if options else "otp"
        return options, default

    def _fetch_platforms(self, session, csrf_token):
        """Fetch ``GET /platforms`` and keep this wizard's supported subset."""
        response = self._mgmt_get("/platforms", session=session, csrf_token=csrf_token) or {}
        if isinstance(response, dict):
            entries = response.get("platforms") or []
        elif isinstance(response, list):
            entries = response
        else:
            entries = []
        available = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = (entry.get("name") or "").strip()
            if name in _PLATFORM_LABELS and entry.get("enabled", True):
                available[name] = entry
        return available

    # ------------------------------------------------------------------
    # Step 3: link the messenger credential
    # ------------------------------------------------------------------
    @api.onchange("link_platform")
    def _onchange_link_platform(self):
        """Refresh auth options + defaults when the platform changes (v2)."""
        stored = []
        try:
            stored = json.loads(self.available_platforms or "[]")
        except (TypeError, ValueError):
            stored = []
        options, default = self._auth_options_for(self.link_platform, stored)
        self.link_auth_options = json.dumps(options)
        self.link_auth_type = default
        self._apply_auth_type_defaults(options, default)

    @api.onchange("link_auth_type")
    def _onchange_link_auth_type(self):
        """Refresh dynamic inputs when the login method changes (v2)."""
        try:
            options = json.loads(self.link_auth_options or "[]")
        except (TypeError, ValueError):
            options = []
        self._apply_auth_type_defaults(options, self.link_auth_type)

    def _apply_auth_type_defaults(self, options, auth_type):
        info = next((o for o in options if o.get("type") == auth_type), {})
        self.link_dynamic_token = False
        self.link_dynamic_token_label = info.get("input_label") or ""
        self.link_dynamic_token_placeholder = info.get("input_placeholder") or ""
        self.link_dynamic_help = info.get("help_text") or info.get("description") or ""

    def _live_platform_names(self):
        """Names from the live GET /platforms list (empty when unknown)."""
        try:
            stored = json.loads(self.available_platforms or "[]")
        except (TypeError, ValueError):
            return []
        return [p.get("name") for p in stored if isinstance(p, dict) and p.get("name")]

    def _selected_auth_info(self):
        try:
            options = json.loads(self.link_auth_options or "[]")
        except (TypeError, ValueError):
            options = []
        return next(
            (o for o in options if o.get("type") == self.link_auth_type), {}
        )

    def action_start_link(self):
        """Start linking via the platform's selected auth method (v2)."""
        self.ensure_one()
        if not self.mgmt_signed_in:
            raise UserError(_("Sign in to Uniom first."))
        platform = self.link_platform
        live = self._live_platform_names()
        if live and platform not in live:
            raise UserError(
                _("This messenger is not available right now. Pick one from the list.")
            )
        if platform not in _PLATFORM_LABELS:
            raise UserError(_("Choose a messenger to link."))
        info = self._selected_auth_info()
        if not info:
            raise UserError(
                _("This login method is not offered for this messenger. Pick one from the list.")
            )
        # token-style auth (bot_api/personal_token): single dynamic input
        if info.get("input_type") == "token" or info.get("requires_bot_token"):
            return self.action_link_dynamic_token()
        if info.get("is_redirect") or info.get("is_oauth"):
            raise UserError(
                _(
                    "This login method opens the Uniom dashboard in a browser. "
                    "Link this account at %(url)s, then connect it here with "
                    "an API key.",
                    url="https://uniom.ir",
                )
            )
        phone = _normalize_phone(self.link_phone)
        session = self._management_session()
        response = (
            self._mgmt_post(
                "/platforms/%s/link/start" % quote(platform, safe=""),
                {"phone": phone},
                session=session,
                csrf_token=self.mgmt_csrf,
            )
            or {}
        )
        session_id = response.get("session_id")
        if not session_id:
            raise UserError(
                _("Uniom did not return a linking session. Please try again.")
            )
        # verification_mode is authoritative (v2); dialog.mode is legacy
        mode = (response.get("verification_mode") or "otp").lower()
        dialog = response.get("dialog") or {}
        if mode == "otp":
            step = "otp"
        elif mode == "password":
            step = "password"
        elif mode in ("qr", "pair_code"):
            # WhatsApp-style: code shown, OTP field hidden, same verify step
            step = "otp"
        else:
            raise UserError(
                _(
                    "Uniom asked for a '%(mode)s' verification, which this "
                    "wizard does not support. Link this account in the Uniom "
                    "dashboard instead.",
                    mode=mode,
                )
            )
        self.write(
            {
                "link_phone": phone,
                "link_phone_display": response.get("phone") or phone,
                "link_session_id": session_id,
                "verification_mode": mode,
                "link_pair_code": response.get("pair_code")
                or dialog.get("pair_code")
                or False,
                "link_qr_link": response.get("qr_link")
                or dialog.get("qr_link")
                or False,
                "link_otp": False,
                "link_password": False,
                "link_credential_id": False,
                "mgmt_cookies": self._dump_cookies(session),
                "step": step,
                "link_message": response.get("message") or False,
            }
        )
        return self._reopen_wizard()

    def action_verify_link(self):
        """Submit the messenger OTP (or move on to the password step)."""
        self.ensure_one()
        if not self.mgmt_signed_in or not self.link_session_id:
            raise UserError(_("Start linking the messenger account first."))
        # v2: qr/pair_code modes post an empty OTP (user confirms on phone)
        needs_otp = (self.verification_mode or "otp").lower() not in ("qr", "pair_code")
        otp = _normalize_otp(self.link_otp) if needs_otp else ""
        session = self._management_session()
        response = (
            self._mgmt_post(
                "/platforms/%s/link/verify" % quote(self.link_platform or "", safe=""),
                {"session_id": self.link_session_id, "otp": otp},
                session=session,
                csrf_token=self.mgmt_csrf,
            )
            or {}
        )
        self._save_cookies(session)
        self._apply_verify_response(response)
        return self._reopen_wizard()

    def action_verify_password(self):
        """Submit the messenger two-step password."""
        self.ensure_one()
        if not self.mgmt_signed_in or not self.link_session_id:
            raise UserError(_("Start linking the messenger account first."))
        password = (self.link_password or "").strip()
        if not password:
            raise UserError(_("Enter your two-step password."))
        session = self._management_session()
        response = (
            self._mgmt_post(
                "/platforms/%s/link/verify" % quote(self.link_platform or "", safe=""),
                {
                    "session_id": self.link_session_id,
                    "otp": "",
                    "password": password,
                },
                session=session,
                csrf_token=self.mgmt_csrf,
            )
            or {}
        )
        self._save_cookies(session)
        if response.get("password_required"):
            self.write(
                {
                    "step": "password",
                    "link_password": False,
                    "link_message": response.get("message")
                    or _("The password was not accepted. Please try again."),
                }
            )
            return self._reopen_wizard()
        self._apply_verify_response(response)
        return self._reopen_wizard()

    def action_show_bot_token(self):
        """Switch to the bot-token alternative for the chosen platform."""
        self.ensure_one()
        if not self.mgmt_signed_in:
            raise UserError(_("Sign in to Uniom first."))
        if self.link_platform not in _PLATFORM_LABELS:
            raise UserError(_("Choose a messenger to link."))
        self.write(
            {
                "step": "bot_token",
                "link_otp": False,
                "link_password": False,
                "link_bot_token": False,
                "link_message": _(
                    "Paste the token issued by the messenger's bot father."
                ),
            }
        )
        return self._reopen_wizard()

    def action_back_to_link_phone(self):
        """Return from the bot-token screen to the phone/OTP link form."""
        self.ensure_one()
        self.write(
            {
                "step": "draft",
                "link_session_id": False,
                "verification_mode": False,
                "link_otp": False,
                "link_password": False,
                "link_bot_token": False,
                "link_message": False,
            }
        )
        return self._reopen_wizard()

    def action_link_dynamic_token(self):
        """Link via the platform's token-style auth (endpoint from v2)."""
        self.ensure_one()
        info = self._selected_auth_info()
        token = (self.link_dynamic_token or "").strip()
        if not token:
            raise UserError(
                self.link_dynamic_token_label
                and _("Enter %(label)s.", label=self.link_dynamic_token_label)
                or _("Enter the token.")
            )
        session = self._management_session()
        endpoint = info.get("api_endpoint") or (
            "/platforms/%s/link/bot" % quote(self.link_platform or "", safe="")
        )
        body_field = "bot_token" if info.get("requires_bot_token") else "token"
        response = (
            self._mgmt_post(
                endpoint, {body_field: token},
                session=session, csrf_token=self.mgmt_csrf,
            )
            or {}
        )
        self._save_cookies(session)
        credential_id = response.get("credential_id")
        if not credential_id:
            raise UserError(
                response.get("message") or _("Uniom did not confirm the bot link.")
            )
        self._complete_link(response)
        return self._reopen_wizard()

    def action_link_bot(self):
        """Link a bot credential with its BotFather token."""
        self.ensure_one()
        if not self.mgmt_signed_in:
            raise UserError(_("Sign in to Uniom first."))
        platform = self.link_platform
        if platform not in _PLATFORM_LABELS:
            raise UserError(_("Choose a messenger to link."))
        bot_token = (self.link_bot_token or "").strip()
        if not bot_token:
            raise UserError(_("Enter the bot token."))
        session = self._management_session()
        response = (
            self._mgmt_post(
                "/platforms/%s/link/bot" % quote(platform, safe=""),
                {"bot_token": bot_token},
                session=session,
                csrf_token=self.mgmt_csrf,
            )
            or {}
        )
        self._save_cookies(session)
        credential_id = response.get("credential_id")
        if not credential_id:
            raise UserError(
                response.get("message") or _("Uniom did not confirm the bot link.")
            )
        bot = response.get("bot") or {}
        display = (
            bot.get("username")
            or bot.get("first_name")
            or ("bot_%s" % bot.get("id") if bot.get("id") else False)
        )
        completed = dict(response)
        completed["phone"] = completed.get("phone") or display
        self._complete_link(completed)
        return self._reopen_wizard()

    def _apply_verify_response(self, response):
        """Advance the link state machine from a ``link/verify`` answer."""
        if response.get("session_id"):
            self.link_session_id = response["session_id"]
        message = response.get("message") or False
        if response.get("password_required"):
            self.write(
                {
                    "step": "password",
                    "link_otp": False,
                    "link_password": False,
                    "link_message": message,
                }
            )
            return
        if response.get("otp_required"):
            self.write(
                {
                    "step": "otp",
                    "link_otp": False,
                    "link_message": message,
                }
            )
            return
        if response.get("credential_id"):
            self._complete_link(response)
            return
        if response.get("status") == "pending" or response.get("verified") is False:
            self.write({"link_message": message})
            return
        raise UserError(
            message or _("Uniom did not confirm the messenger link. Please try again.")
        )

    def _complete_link(self, response):
        """Move to the API-key step once a credential id is known."""
        try:
            credential_id = int(response.get("credential_id"))
        except (TypeError, ValueError):
            raise UserError(
                _("Uniom did not return a messenger credential id. Please try again.")
            ) from None
        phone = response.get("phone") or self.link_phone_display or self.link_phone
        self.write(
            {
                "link_credential_id": credential_id,
                "link_phone_display": phone or False,
                "link_phone": self.link_phone or phone or False,
                "link_session_id": False,
                "verification_mode": False,
                "link_otp": False,
                "link_password": False,
                "link_bot_token": False,
                "link_dynamic_token": False,
                "link_pair_code": False,
                "link_qr_link": False,
                "link_message": response.get("message") or False,
                "step": "done",
            }
        )
        return None

    # ------------------------------------------------------------------
    # Step 4: mint the API key and create the Odoo connection
    # ------------------------------------------------------------------
    def action_create_key(self):
        """Create an API key for the linked credential and store it in Odoo."""
        self.ensure_one()
        # serialize concurrent RPCs (double click, automatic retry): the
        # gateway key mint below is not covered by Odoo's rollback, so a
        # second request must see the first one's connection, not mint again
        self.env.cr.execute(
            "SELECT id FROM uniom_link_wizard WHERE id = %s FOR UPDATE", [self.id]
        )
        self.invalidate_recordset(["created_connection_id"])
        if self.created_connection_id:
            return self._reopen_wizard()
        if not self.link_credential_id:
            raise UserError(_("Link a messenger account first."))
        if not self.mgmt_signed_in:
            raise UserError(_("Sign in to Uniom first."))
        name = (self.api_key_name or "").strip()
        if not name:
            raise UserError(_("Give the API key a name."))
        session = self._management_session()
        response = (
            self._mgmt_post(
                "/api_keys",
                {
                    "credential_id": int(self.link_credential_id),
                    "name": name,
                    "scopes": ["read", "write"],
                },
                session=session,
                csrf_token=self.mgmt_csrf,
            )
            or {}
        )
        token = (response.get("api_key") or response.get("token") or "").strip()
        if not token:
            raise UserError(
                _(
                    "Uniom did not return an API key. Create one in the Uniom "
                    "dashboard and connect it with the API-key wizard."
                )
            )
        connection = self.env["uniom.connection"].create(
            self._connection_values(token)
        )
        notes = []
        # test/activate/sync are best effort: each returns None or an error
        # string (never raises, never a silent warning dict)
        err = connection._friendly_call("action_test_connection")
        if err:
            _logger.warning("Uniom: post-link verification failed: %s", err)
            notes.append(_("The new key could not be verified yet: %s", err))
        if connection.inbound_mode == "polling":
            err = connection._friendly_call("action_start_polling")
            if err:
                notes.append(_("Polling could not be started: %s", err))
        else:
            err = connection._friendly_call("action_register_webhook")
            if err:
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
            notes.append(_("Conversations could not be synchronized yet: %s", err))
        # The cookie session, CSRF token, password and OTP are no longer
        # needed: drop them from the transient record as soon as the
        # persistent key exists.
        self.write(
            {
                "created_connection_id": connection.id,
                "mgmt_cookies": False,
                "mgmt_csrf": False,
                "mgmt_signed_in": False,
                "link_password": False,
                "link_otp": False,
                "link_bot_token": False,
                "link_dynamic_token": False,
                "link_pair_code": False,
                "link_qr_link": False,
                "link_session_id": False,
                "verification_mode": False,
                "step": "done",
                "link_message": " ".join(str(note) for note in notes)
                or _("Messenger account linked and API key created."),
            }
        )
        return self._reopen_wizard()

    def _connection_values(self, token):
        label = _PLATFORM_LABELS.get(self.link_platform) or _("Uniom")
        phone = self.link_phone_display or self.link_phone or ""
        if phone:
            name = "%s — %s" % (label, phone)
        else:
            name = _("Uniom %(platform)s", platform=label)
        return {
            "name": name,
            "base_url": self.base_url,
            "api_key": token,
            "platform": self.link_platform or False,
            "inbound_mode": self.inbound_mode or "polling",
            "credential_id": int(self.link_credential_id),
            "credential_phone": phone or False,
            "credential_status": "active",
        }

    def action_open_connection(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Uniom Connection"),
            "res_model": "uniom.connection",
            "res_id": self.created_connection_id.id,
            "view_mode": "form",
            "target": "current",
        }
