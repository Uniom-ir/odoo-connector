# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""The Link Messenger Account wizard, driven end to end against a mocked
management API (never against a real gateway)."""

import json
from contextlib import contextmanager
from unittest.mock import patch
from urllib.parse import urlparse

import requests

from odoo.exceptions import UserError

from odoo.addons.uniom_connector.models.uniom_connection import UniomConnection
from odoo.addons.uniom_connector.models.uniom_tools import UniomAPIError

from .common import BASE_URL, FAKE_KEY, FakeResponse, UniomTestCase

SEND_OTP = {
    "success": True,
    "message": "Code sent",
    "expires_in": 120,
    "client_id": "client-1",
}
LOGIN = {
    # The real gateway puts the JWT in an HttpOnly cookie and returns an
    # empty token in the body; csrf_token mirrors the csrf cookie.
    "access_token": "",
    "token_type": "bearer",
    "user_id": 1,
    "phone": "09123456789",
    "expires_in": 3600,
    "csrf_token": "csrf-1",
}
PLATFORMS = {
    "platforms": [
        {
            "name": "bale",
            "display_name": "Bale",
            "enabled": True,
            "default_auth_type": "otp",
            "auth_types": [
                {"type": "otp", "name": "Phone Code", "requires_phone": True},
                {"type": "bot_api", "name": "Bot Token", "requires_bot_token": True},
            ],
        },
        {"name": "telegram", "display_name": "Telegram", "enabled": True},
        {"name": "other", "display_name": "Other", "enabled": True},
    ]
}
START_OTP = {
    "session_id": "sess-1",
    "message": "Code sent in the messenger",
    "expires_in": 120,
    "verification_mode": "otp",
}
VERIFY_SUCCESS = {
    "success": True,
    "credential_id": 77,
    "platform": "bale",
    "phone": "+989120000000",
    "message": "Messenger account linked",
}
API_KEY = {
    "id": 5,
    "api_key": "uniom_newkey",
    "name": "Odoo",
    "scopes": ["read", "write"],
    "created_at": "2026-01-01T00:00:00Z",
}


def _next_response(responses, path):
    queue = responses.get(path)
    if not queue:
        raise AssertionError("Unexpected management API call: %s" % path)
    item = queue.pop(0) if len(queue) > 1 else queue[0]
    if isinstance(item, Exception):
        raise item
    return item


def _cookie_dict(raw):
    return {
        item["name"]: item["value"]
        for item in json.loads(raw or "[]")
        if item.get("name")
    }


class FakeGateway:
    """Path-scripted stand-in for the gateway, patched at Session.request."""

    def __init__(self, call_responses=None, get_responses=None):
        self.responses = dict(call_responses or {})
        self.responses.update(get_responses or {})
        self.calls = []

    def handle(self, session, method, url, **kwargs):
        path = urlparse(url).path
        self.calls.append(
            {
                "method": method,
                "url": url,
                "path": path,
                "payload": kwargs.get("json"),
                "headers": dict(kwargs.get("headers") or {}),
                "cookies": {
                    cookie.name: cookie.value for cookie in session.cookies
                },
            }
        )
        item = _next_response(self.responses, path)
        if isinstance(item, Exception):
            raise item
        payload = item if isinstance(item, dict) else {}
        if path == "/auth/sendOtp":
            client_id = payload.get("client_id")
            if client_id:
                session.cookies.set("otp_client_id", client_id)
        elif path == "/auth/login":
            # the gateway deletes the OTP cookie on login and sets the JWT +
            # CSRF cookies; the JWT is deliberately absent from the body
            session.cookies.pop("otp_client_id", None)
            session.cookies.set("access_token", "jwt-token")
            session.cookies.set("csrf_token", payload.get("csrf_token") or "csrf-1")
        if isinstance(item, dict):
            return FakeResponse(dict(item))
        return item

    def calls_to(self, path):
        return [call for call in self.calls if call["path"] == path]


@contextmanager
def mocked_management_api(call_responses=None, get_responses=None):
    gateway = FakeGateway(call_responses, get_responses)

    def fake_request(session, method, url, **kwargs):
        return gateway.handle(session, method, url, **kwargs)

    with patch.object(requests.Session, "request", fake_request), patch.object(
        UniomConnection, "action_test_connection", lambda connection: True
    ), patch.object(
        UniomConnection, "action_sync_dialogs", lambda connection: True
    ), patch.object(
        UniomConnection, "action_start_polling", lambda connection: True
    ), patch.object(
        UniomConnection, "action_register_webhook", lambda connection: True
    ):
        yield gateway


class TestUniomLinkWizard(UniomTestCase):
    def _wizard(self, **values):
        values.setdefault("base_url", BASE_URL)
        return self.env["uniom.link.wizard"].create(values)

    def _signed_in_wizard(self, **values):
        values.setdefault(
            "mgmt_cookies",
            json.dumps(
                [
                    {"name": "access_token", "value": "jwt-token", "path": "/"},
                    {"name": "csrf_token", "value": "csrf-1", "path": "/"},
                ]
            ),
        )
        values.setdefault("mgmt_csrf", "csrf-1")
        values.setdefault("mgmt_signed_in", True)
        values.setdefault(
            "available_platforms",
            json.dumps(
                [
                    {
                        "name": "bale",
                        "display_name": "Bale",
                        "auth_types": [
                            {"type": "otp", "name": "Phone Code"},
                        ],
                        "default_auth_type": "otp",
                    }
                ]
            ),
        )
        values.setdefault(
            "link_auth_options",
            json.dumps([{"type": "otp", "name": "Phone Code"}]),
        )
        values.setdefault("link_auth_type", "otp")
        return self._wizard(**values)

    def test_link_flow_end_to_end(self):
        wizard = self._wizard(uniom_phone="09123456789")
        with mocked_management_api(
            call_responses={
                "/auth/sendOtp": [dict(SEND_OTP)],
                "/auth/login": [dict(LOGIN)],
                "/platforms/bale/link/start": [dict(START_OTP)],
                "/platforms/bale/link/verify": [dict(VERIFY_SUCCESS)],
                "/api_keys": [dict(API_KEY)],
            },
            get_responses={"/platforms": [dict(PLATFORMS)]},
        ) as api:
            action = wizard.action_send_otp()
            self.assertEqual(action["res_model"], "uniom.link.wizard")
            self.assertEqual(action["res_id"], wizard.id)
            self.assertEqual(wizard.uniom_phone, "+989123456789")
            self.assertEqual(wizard.step, "otp")
            self.assertFalse(wizard.mgmt_signed_in)
            cookies = _cookie_dict(wizard.mgmt_cookies)
            self.assertEqual(cookies.get("otp_client_id"), "client-1")
            send_call = api.calls_to("/auth/sendOtp")[0]
            self.assertEqual(send_call["url"], BASE_URL + "/auth/sendOtp")
            self.assertEqual(send_call["payload"], {"phone": "+989123456789"})
            self.assertNotIn("X-CSRF-Token", send_call["headers"])

            wizard.uniom_otp = "123456"
            wizard.action_login()
            self.assertTrue(wizard.mgmt_signed_in)
            self.assertEqual(wizard.step, "draft")
            self.assertEqual(wizard.mgmt_csrf, "csrf-1")
            self.assertEqual(wizard.link_platform, "bale")
            cookies = _cookie_dict(wizard.mgmt_cookies)
            self.assertEqual(cookies.get("access_token"), "jwt-token")
            self.assertEqual(cookies.get("csrf_token"), "csrf-1")
            self.assertNotIn("otp_client_id", cookies)
            login_call = api.calls_to("/auth/login")[0]
            self.assertEqual(
                login_call["payload"],
                {"phone": "+989123456789", "otp": "123456"},
            )
            # the OTP cookie was restored from mgmt_cookies into the session
            self.assertEqual(
                login_call["cookies"].get("otp_client_id"), "client-1"
            )
            self.assertNotIn("X-CSRF-Token", login_call["headers"])
            platforms_call = api.calls_to("/platforms")[0]
            self.assertEqual(platforms_call["method"], "GET")
            self.assertIsNone(platforms_call["payload"])
            # GET carries cookies but never the CSRF header
            self.assertEqual(
                platforms_call["cookies"].get("access_token"), "jwt-token"
            )
            self.assertNotIn("X-CSRF-Token", platforms_call["headers"])

            wizard.write({"link_phone": "09120000000"})
            wizard.action_start_link()
            self.assertEqual(wizard.step, "otp")
            self.assertEqual(wizard.link_session_id, "sess-1")
            self.assertEqual(wizard.link_phone, "+989120000000")
            start_call = api.calls_to("/platforms/bale/link/start")[0]
            self.assertEqual(start_call["payload"], {"phone": "+989120000000"})
            self.assertEqual(start_call["headers"].get("X-CSRF-Token"), "csrf-1")
            self.assertEqual(
                start_call["cookies"].get("access_token"), "jwt-token"
            )

            wizard.link_otp = "4321"
            wizard.action_verify_link()
            self.assertEqual(wizard.step, "done")
            self.assertEqual(wizard.link_credential_id, 77)
            verify_call = api.calls_to("/platforms/bale/link/verify")[0]
            self.assertEqual(
                verify_call["payload"],
                {"session_id": "sess-1", "otp": "4321"},
            )
            self.assertEqual(verify_call["headers"].get("X-CSRF-Token"), "csrf-1")

            action = wizard.action_create_key()
            self.assertEqual(action["res_model"], "uniom.link.wizard")
            self.assertEqual(action["res_id"], wizard.id)
            connection = wizard.created_connection_id
            self.assertTrue(connection)
            self.assertEqual(connection.api_key, "uniom_newkey")
            self.assertEqual(connection.credential_id, 77)
            self.assertEqual(connection.credential_phone, "+989120000000")
            self.assertEqual(connection.credential_status, "active")
            self.assertEqual(connection.platform, "bale")
            self.assertEqual(connection.base_url, BASE_URL)
            key_call = api.calls_to("/api_keys")[0]
            self.assertEqual(key_call["headers"].get("X-CSRF-Token"), "csrf-1")
            self.assertEqual(
                key_call["payload"],
                {
                    "credential_id": 77,
                    "name": "Odoo",
                    "scopes": ["read", "write"],
                },
            )
            self.assertFalse(wizard.mgmt_cookies)
            self.assertFalse(wizard.mgmt_csrf)
            self.assertFalse(wizard.mgmt_signed_in)
            self.assertFalse(wizard.link_password)
            self.assertNotIn("jwt-token", repr(wizard.read()[0]))
            self.assertNotIn("csrf-1", repr(wizard.read()[0]))
            self.assertNotIn("access_token", repr(connection.read()[0]))
            self.assertNotIn("jwt-token", repr(connection.read()[0]))
            self.assertNotIn("csrf-1", repr(connection.read()[0]))

    def test_login_uses_httponly_cookie_not_body_token(self):
        wizard = self._wizard(
            uniom_phone="+989123456789",
            uniom_otp="1234",
            otp_client_id="client-1",
            mgmt_cookies=json.dumps(
                [{"name": "otp_client_id", "value": "client-1", "path": "/"}]
            ),
        )
        self.assertEqual(LOGIN["access_token"], "")
        with mocked_management_api(
            call_responses={"/auth/login": [dict(LOGIN)]},
            get_responses={"/platforms": [dict(PLATFORMS)]},
        ):
            wizard.action_login()
        self.assertTrue(wizard.mgmt_signed_in)
        self.assertEqual(
            _cookie_dict(wizard.mgmt_cookies).get("access_token"), "jwt-token"
        )

    def test_resend_otp_restores_cookie_session(self):
        wizard = self._wizard(uniom_phone="09123456789")
        again = dict(SEND_OTP)
        again["client_id"] = "client-2"
        with mocked_management_api(
            call_responses={"/auth/sendOtp": [dict(SEND_OTP), again]}
        ) as api:
            wizard.action_send_otp()
            wizard.action_resend_otp()
        self.assertEqual(
            _cookie_dict(wizard.mgmt_cookies).get("otp_client_id"), "client-2"
        )
        calls = api.calls_to("/auth/sendOtp")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["cookies"].get("otp_client_id"), "client-1")
        self.assertNotIn("X-CSRF-Token", calls[1]["headers"])

    def test_wrong_otp_raises_user_error(self):
        wizard = self._wizard(
            uniom_phone="09123456789",
            uniom_otp="9999",
            otp_client_id="client-1",
        )
        with mocked_management_api(
            call_responses={"/auth/login": [UniomAPIError("Invalid OTP", error_code=401)]}
        ):
            with self.assertRaises(UserError):
                wizard.action_login()
        self.assertFalse(wizard.mgmt_signed_in)

    def test_password_required_path(self):
        wizard = self._signed_in_wizard(
            link_platform="bale",
            link_phone="+989120000000",
        )
        with mocked_management_api(
            call_responses={
                "/platforms/bale/link/start": [dict(START_OTP)],
                "/platforms/bale/link/verify": [
                    {"password_required": True, "message": "2FA password required"},
                    dict(VERIFY_SUCCESS),
                ],
            }
        ) as api:
            wizard.action_start_link()
            self.assertEqual(wizard.step, "otp")
            wizard.link_otp = "1234"
            wizard.action_verify_link()
            self.assertEqual(wizard.step, "password")
            self.assertEqual(wizard.link_session_id, "sess-1")
            self.assertFalse(wizard.link_otp)

            wizard.link_password = "secret-password"
            wizard.action_verify_password()
            calls = api.calls_to("/platforms/bale/link/verify")
            self.assertEqual(
                calls[1]["payload"],
                {
                    "session_id": "sess-1",
                    "otp": "",
                    "password": "secret-password",
                },
            )
            self.assertEqual(calls[1]["headers"].get("X-CSRF-Token"), "csrf-1")
            self.assertEqual(
                calls[1]["cookies"].get("access_token"), "jwt-token"
            )
        self.assertEqual(wizard.step, "done")
        self.assertEqual(wizard.link_credential_id, 77)
        self.assertFalse(wizard.link_password)
        self.assertNotIn("secret-password", repr(wizard.read()[0]))

    def test_start_link_rejects_unlisted_platform(self):
        wizard = self._signed_in_wizard(
            link_platform="telegram", link_phone="+989120000000"
        )
        with mocked_management_api(call_responses={}):
            with self.assertRaises(UserError):
                wizard.action_start_link()

    def test_start_link_rejects_unlisted_auth_type(self):
        wizard = self._signed_in_wizard(
            link_platform="bale",
            link_phone="+989120000000",
            link_auth_type="oauth_code",
        )
        with mocked_management_api(call_responses={}):
            with self.assertRaises(UserError):
                wizard.action_start_link()

    def test_bot_token_path_creates_connection(self):
        wizard = self._signed_in_wizard(link_platform="telegram")
        with mocked_management_api(
            call_responses={
                "/platforms/telegram/link/bot": [
                    {
                        "status": "success",
                        "credential_id": 99,
                        "bot": {"id": 123, "username": "mybot"},
                        "message": "Bot linked",
                    }
                ],
                "/api_keys": [dict(API_KEY)],
            }
        ) as api:
            wizard.action_show_bot_token()
            self.assertEqual(wizard.step, "bot_token")
            wizard.link_bot_token = "123:ABC"
            wizard.action_link_bot()
            self.assertEqual(wizard.step, "done")
            self.assertEqual(wizard.link_credential_id, 99)
            self.assertEqual(wizard.link_phone_display, "mybot")
            self.assertFalse(wizard.link_bot_token)
            bot_call = api.calls_to("/platforms/telegram/link/bot")[0]
            self.assertEqual(bot_call["payload"], {"bot_token": "123:ABC"})
            self.assertEqual(bot_call["headers"].get("X-CSRF-Token"), "csrf-1")

            wizard.action_create_key()
        connection = wizard.created_connection_id
        self.assertEqual(connection.credential_id, 99)
        self.assertEqual(connection.credential_phone, "mybot")
        self.assertEqual(connection.platform, "telegram")
        self.assertNotIn("123:ABC", repr(wizard.read()[0]))
        self.assertNotIn("123:ABC", repr(connection.read()[0]))


class FakeSession:
    """Minimal duck-typed requests.Session for helper-level assertions."""

    def __init__(self, item):
        self.item = item
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if isinstance(self.item, Exception):
            raise self.item
        return self.item


class TestManagementHelper(UniomTestCase):
    def _connection(self, base_url=BASE_URL):
        return self.env["uniom.connection"].create(
            {"name": "Management helper", "base_url": base_url, "api_key": FAKE_KEY}
        )

    def test_mgmt_call_posts_with_csrf_and_no_bearer(self):
        session = FakeSession(FakeResponse({"success": True}))
        connection = self._connection()
        result = connection._mgmt_call(
            "/auth/sendOtp",
            {"phone": "+989123456789"},
            session=session,
            csrf_token="csrf-1",
        )
        self.assertEqual(result, {"success": True})
        call = session.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], BASE_URL + "/auth/sendOtp")
        self.assertEqual(call["headers"]["X-CSRF-Token"], "csrf-1")
        self.assertEqual(call["json"], {"phone": "+989123456789"})
        self.assertNotIn("Authorization", call["headers"])

    def test_mgmt_get_never_sends_csrf_header(self):
        session = FakeSession(FakeResponse({"platforms": []}))
        connection = self._connection()
        result = connection._mgmt_get(
            "/platforms", session=session, csrf_token="csrf-1"
        )
        self.assertEqual(result, {"platforms": []})
        call = session.calls[0]
        self.assertEqual(call["method"], "GET")
        self.assertNotIn("X-CSRF-Token", call["headers"])
        self.assertNotIn("json", call)

    def test_mgmt_call_strips_bot_suffix_from_base(self):
        session = FakeSession(FakeResponse({"ok": True}))
        connection = self._connection(BASE_URL + "/bot")
        connection._mgmt_get("/platforms", session=session)
        self.assertEqual(session.calls[0]["url"], BASE_URL + "/platforms")

    def test_mgmt_call_raises_on_http_error(self):
        session = FakeSession(FakeResponse({"detail": "Invalid OTP"}, status_code=401))
        connection = self._connection()
        with self.assertRaises(UniomAPIError) as caught:
            connection._mgmt_call("/auth/login", {"otp": "bad"}, session=session)
        self.assertEqual(caught.exception.error_code, 401)
        self.assertIn("Invalid OTP", str(caught.exception))

    def test_mgmt_call_raises_on_ok_false(self):
        session = FakeSession(
            FakeResponse(
                {"ok": False, "error_code": 429, "description": "Too many requests"}
            )
        )
        connection = self._connection()
        with self.assertRaises(UniomAPIError) as caught:
            connection._mgmt_get("/platforms", session=session)
        self.assertEqual(caught.exception.error_code, 429)

    def test_error_text_mirrors_panel_extraction_order(self):
        extract = UniomConnection._mgmt_error_text
        self.assertEqual(extract({"detail": {"message": "nested"}}), "nested")
        self.assertEqual(extract({"detail": {"description": "nested desc"}}), "nested desc")
        self.assertEqual(
            extract({"detail": "raw detail", "description": "top", "message": "msg"}),
            "raw detail",
        )
        self.assertEqual(
            extract({"description": "top desc", "message": "msg"}), "top desc"
        )
        self.assertEqual(extract({"message": "msg", "error": "err"}), "msg")
        self.assertEqual(extract({"error": "err"}), "err")
        self.assertEqual(
            extract({"detail": [{"msg": "one"}, {"message": "two"}, "three"]}),
            "one, two, three",
        )
        # an array detail overrides even a top-level description
        self.assertEqual(
            extract({"detail": [{"msg": "array wins"}], "description": "top"}),
            "array wins",
        )
