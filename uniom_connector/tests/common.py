# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Shared test helpers: a fake Bot API transport and sample payloads.

The transport patch also pins DNS resolution to a public address so the
suite never performs real lookups (the URL validator resolves hosts).
"""

from contextlib import contextmanager
from unittest.mock import patch

from odoo.tests import TransactionCase

from odoo.addons.uniom_connector.models import uniom_connection as uniom_connection_module
from odoo.addons.uniom_connector.models import uniom_tools as uniom_tools_module

FAKE_KEY = "uniom_" + "ab" * 24
# deliberately not a Uniom key, used to assert the format constraint
INVALID_KEY = "pat_" + "cd" * 24
BASE_URL = "https://api.uniom.ir"


def ok_response(result=None):
    return {"ok": True, "result": result or {"message_id": 42, "chat": {"id": 987}}}


def error_response(code, description, parameters=None):
    return {"ok": False, "error_code": code, "description": description, "parameters": parameters or {}}


class FakeResponse:
    def __init__(self, payload, status_code=200, reason=None):
        self._payload = payload
        self.status_code = status_code
        self.reason = reason

    def json(self):
        return self._payload


class FakeTransport:
    """Records Bot API calls and replays scripted responses.

    ``script`` is a list of FakeResponse (or Exception) items consumed one
    per request; when exhausted, the last entry repeats.
    """

    def __init__(self, script=None):
        self.script = list(script or [FakeResponse(ok_response())])
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        index = min(len(self.calls) - 1, len(self.script) - 1)
        item = self.script[index]
        if isinstance(item, Exception):
            raise item
        return item


def _fake_resolver(address="93.184.216.34"):
    def resolver(hostname, *args, **kwargs):
        return [(2, 1, 6, "", (address, 443))]
    return resolver


@contextmanager
def patched_transport(script=None):
    transport = FakeTransport(script)
    with patch.object(uniom_connection_module.requests, "post", transport), \
            patch.object(uniom_tools_module.socket, "getaddrinfo", _fake_resolver()):
        yield transport


class UniomTestCase(TransactionCase):
    """Base class for the module's tests: pins DNS resolution to a public
    address so connection creation (base URL constraint) never performs a
    real lookup, on- or offline."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        resolver = patch.object(
            uniom_tools_module.socket, "getaddrinfo", _fake_resolver()
        )
        resolver.start()
        cls.addClassCleanup(resolver.stop)
