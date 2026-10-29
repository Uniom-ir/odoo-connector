# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
from odoo.exceptions import ValidationError

from odoo.addons.uniom_connector.models.uniom_tools import UniomAPIError

from .common import (
    BASE_URL,
    FAKE_KEY,
    INVALID_KEY,
    FakeResponse,
    UniomTestCase,
    error_response,
    ok_response,
    patched_transport,
)


class TestConnection(UniomTestCase):
    def _create_connection(self, **kwargs):
        values = {
            "name": "Test Bale",
            "base_url": BASE_URL,
            "api_key": FAKE_KEY,
        }
        values.update(kwargs)
        return self.env["uniom.connection"].create(values)

    def test_endpoint_url_is_telegram_style(self):
        connection = self._create_connection()
        url = connection._build_endpoint("sendMessage")
        self.assertEqual(url, "%s/bot%s/sendMessage" % (BASE_URL, FAKE_KEY))

    def test_call_success_returns_result(self):
        connection = self._create_connection()
        with patched_transport(
            [FakeResponse(ok_response({"message_id": 7, "chat": {"id": 5}}))]
        ) as transport:
            result = connection._call("sendMessage", {"chat_id": "@chan", "text": "hi"})
            self.assertEqual(result["message_id"], 7)
            self.assertIn("/bot", transport.calls[0]["url"])
            self.assertEqual(transport.calls[0]["json"]["chat_id"], "@chan")

    def test_call_error_envelope_maps_description(self):
        connection = self._create_connection()
        with patched_transport(
            [FakeResponse(error_response(400, "Bad Request: chat not found"), status_code=400)]
        ):
            with self.assertRaises(UniomAPIError) as caught:
                connection._call("sendMessage", {"chat_id": "xx", "text": "hi"})
            self.assertEqual(caught.exception.error_code, 400)
            self.assertFalse(caught.exception.transient)

    def test_call_429_is_transient_with_retry_after(self):
        connection = self._create_connection()
        with patched_transport(
            [FakeResponse(
                error_response(429, "Too Many Requests", {"retry_after": 120}), status_code=429
            )]
        ):
            with self.assertRaises(UniomAPIError) as caught:
                connection._call("sendMessage", {"chat_id": "@chan", "text": "hi"})
            self.assertTrue(caught.exception.transient)
            self.assertEqual(caught.exception.retry_after, 120)

    def test_call_redirect_refused(self):
        connection = self._create_connection()
        with patched_transport([FakeResponse({}, status_code=302, reason="Found")]):
            with self.assertRaises(UniomAPIError) as caught:
                connection._call("getMe")
            self.assertFalse(caught.exception.transient)

    def test_api_key_prefix_enforced(self):
        with self.assertRaises(ValidationError):
            self._create_connection(api_key=INVALID_KEY)

    def test_base_url_must_be_public(self):
        with self.assertRaises(ValidationError):
            self._create_connection(base_url="http://localhost:8069")

    def test_test_connection_stores_identity(self):
        connection = self._create_connection()
        with patched_transport(
            [FakeResponse(ok_response({"id": 15, "first_name": "My Bale Account"}))]
        ):
            connection.action_test_connection()
        self.assertEqual(connection.account_display, "My Bale Account")
