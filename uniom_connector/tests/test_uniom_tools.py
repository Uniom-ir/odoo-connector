# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase

from odoo.addons.uniom_connector.models import uniom_tools
from odoo.addons.uniom_connector.models.uniom_tools import canonicalize_chat_id, parse_manual_chat_ids


def _fake_resolver(addresses):
    def resolver(hostname):
        return [(0, 0, 0, "", (address, 0)) for address in addresses]
    return resolver


class TestChatIdCanonicalization(TransactionCase):
    def test_iranian_phone_formats(self):
        self.assertEqual(canonicalize_chat_id("09123456789"), "+989123456789")
        self.assertEqual(canonicalize_chat_id("989123456789"), "+989123456789")
        self.assertEqual(canonicalize_chat_id("+989123456789"), "+989123456789")
        self.assertEqual(canonicalize_chat_id("+98 912 345 6789"), "+989123456789")

    def test_channels_and_ids(self):
        self.assertEqual(canonicalize_chat_id("@mychannel"), "@mychannel")
        self.assertEqual(canonicalize_chat_id("mychannel"), False)
        self.assertEqual(canonicalize_chat_id("#12345"), "#12345")
        self.assertEqual(canonicalize_chat_id("-1001234567890"), "-1001234567890")
        self.assertEqual(canonicalize_chat_id("1559499"), "1559499")

    def test_invalid(self):
        self.assertFalse(canonicalize_chat_id(""))
        self.assertFalse(canonicalize_chat_id("not-a-chat"))
        self.assertFalse(canonicalize_chat_id("+abc"))
        self.assertFalse(canonicalize_chat_id("+12345"))  # too short for E.164

    def test_manual_list(self):
        values = "@chan\n09123456789, garbage; -100999"
        self.assertEqual(
            parse_manual_chat_ids(values),
            ["@chan", "+989123456789", "-100999"],
        )


class TestUrlValidation(TransactionCase):
    def test_rejects_non_http(self):
        with self.assertRaises(ValidationError):
            uniom_tools.validate_public_http_url("ftp://api.uniom.ir")

    def test_rejects_localhost_and_private(self):
        for url in (
            "http://localhost:8069/uniom/webhook/1",
            "http://127.0.0.1/webhook",
            "http://192.168.1.10/webhook",
            "http://10.0.0.5/webhook",
            "http://uniom.internal/",
            "https://mybox.local/",
        ):
            with self.assertRaises(ValidationError, msg=url):
                uniom_tools.validate_public_http_url(url)

    def test_rejects_private_resolution(self):
        with patch.object(
            uniom_tools.socket, "getaddrinfo", _fake_resolver(["192.168.0.7"])
        ):
            with self.assertRaises(ValidationError):
                uniom_tools.validate_public_http_url("https://gateway.example.com")

    def test_accepts_public_host(self):
        with patch.object(
            uniom_tools.socket, "getaddrinfo", _fake_resolver(["185.51.200.10"])
        ):
            self.assertEqual(
                uniom_tools.validate_public_http_url("https://api.uniom.ir"),
                "https://api.uniom.ir",
            )
