# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Pure helpers for the Uniom connector: chat id canonicalization, base URL
validation and the API error type shared by every model."""

import ipaddress
import re
import socket
from urllib.parse import urlparse

from odoo import _
from odoo.exceptions import UserError, ValidationError

DEFAULT_BASE_URL = "https://api.uniom.ir"

# model -> standard PDF report worth attaching (the only reports the module
# will ever render; also the guard against rendering arbitrary reports)
REPORT_BY_MODEL = {
    "sale.order": "sale.action_report_saleorder",
    "account.move": "account.account_invoices",
    "account.payment": "account.action_report_payment_receipt",
    "stock.picking": "stock.action_report_delivery",
}

# never schedule a retry further out than this (minutes), whatever the
# gateway's retry_after says
MAX_RETRY_DELAY_MINUTES = 1440

# Uniom accepts several destination spellings (Bot API compatible):
#   +989123456789   E.164 private chat
#   09123456789     local Iranian mobile -> canonicalized to +98...
#   989123456789    bare international -> canonicalized to +98...
#   -1001234567890  numeric group/channel id
#   @username       public channel or group
#   #12345          user id
#   u0.../g0...     platform GUIDs kept verbatim
_NUMERIC_RE = re.compile(r"^-?\d+$")
_GUID_RE = re.compile(r"^(?:u|g|c|b|r)0[a-z0-9]+$")


def canonicalize_chat_id(value):
    """Return the canonical Uniom chat id for ``value``, or ``False`` when it
    cannot be interpreted at all."""
    value = (value or "").strip()
    if not value:
        return False
    if _NUMERIC_RE.match(value):
        # local Iranian mobile: 09xxxxxxxxx (11 digits) -> +989xxxxxxxxx
        if len(value) == 11 and value.startswith("0"):
            return "+98" + value[1:]
        if len(value) == 12 and value.startswith("98"):
            return "+" + value
        return value
    if value.startswith(("@", "#")):
        return value if len(value) > 1 else False
    if value.startswith("+"):
        digits = value[1:].replace(" ", "")
        if digits.isdigit() and 7 <= len(digits) <= 15:
            return "+" + digits
        return False
    if _GUID_RE.match(value):
        return value
    return False


def parse_manual_chat_ids(value):
    """Parse a free-text list of destinations (one per line or comma
    separated) into canonical chat ids. Invalid entries are skipped."""
    results = []
    for chunk in re.split(r"[\n,;]+", value or ""):
        chat_id = canonicalize_chat_id(chunk)
        if chat_id:
            results.append(chat_id)
    return results


def _private_ip_detected(hostname):
    """Resolve *hostname* and report whether any resolved address is a
    loopback, private, link-local or otherwise reserved address."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        # Unresolvable hosts are rejected too: the request could never
        # succeed and a failure here keeps behaviour predictable.
        return True
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if not ip.is_global:
            return True
    return False


def validate_public_http_url(url, resolve_dns=True):
    """Validate a server-side request target. Only http/https is allowed and
    localhost, loopback, private, link-local and reserved targets are refused
    (SSRF hardening, mirroring the Uniom gateway's own webhook policy).

    The URL is additionally parsed the way the HTTP stack (urllib3) parses
    it: backslashes and control characters make different parsers disagree
    about the host being dialed, so they are rejected outright.
    """
    url = (url or "").strip()
    if any(char in url for char in "\\\t\r\n\0"):
        raise ValidationError(_("Invalid URL: control characters are not allowed."))
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError(
            _("Only http:// and https:// URLs are allowed, got: %s", url or _("empty"))
        )
    hostname = parsed.hostname
    if not hostname:
        raise ValidationError(_("The URL %s has no host.", url))
    # cross-check with the transport's own parser: when it disagrees with
    # urlparse about the host, the URL is ambiguous and must be refused
    try:
        from urllib3.util import parse_url as parse_url_transport

        transport_host = parse_url_transport(url).host
        if transport_host != hostname:
            raise ValidationError(
                _("Ambiguous URL %s: the HTTP stack resolves a different host than the validator.", url)
            )
    except ImportError:
        pass
    if hostname in ("localhost",) or hostname.endswith(".local") or hostname.endswith(".internal"):
        raise ValidationError(
            _("Host %s is not allowed: private or local hosts are refused.", hostname)
        )
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None
    if ip is not None and not ip.is_global:
        raise ValidationError(
            _("IP address %s is not allowed: only public addresses are accepted.", hostname)
        )
    if ip is None and resolve_dns and _private_ip_detected(hostname):
        raise ValidationError(
            _("Host %s resolves to a private or reserved address and is refused.", hostname)
        )
    return url


class UniomAPIError(UserError):
    """The Uniom Bot API answered ``ok: false`` or the HTTP transport failed.

    Attributes carry what the queue needs to decide between an immediate
    failure, a delayed retry, or "outcome unknown, never retry" (504):
    """

    def __init__(self, message, error_code=None, retry_after=None, transient=None):
        super().__init__(message)
        self.error_code = error_code
        self.retry_after = retry_after
        # ``transient`` defaults to the Uniom error semantics documented in
        # BOT_API.md: 429 and 5xx (except 504) are retry-worthy, 4xx are not.
        if transient is None:
            transient = error_code == 429 or (
                error_code is not None and 500 <= error_code < 600 and error_code != 504
            )
        self.transient = transient
