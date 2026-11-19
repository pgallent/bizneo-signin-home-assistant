"""Tests for safe Bizneo response classification."""

from __future__ import annotations

import importlib.util
import unittest
from unittest.mock import AsyncMock, patch

if importlib.util.find_spec("aiohttp") is None:
    raise unittest.SkipTest("aiohttp no está instalado en el entorno local")

from aiohttp import ServerDisconnectedError

from custom_components.bizneo_signin.api import (
    BizneoApiClient,
    BizneoAuthError,
    BizneoConfigurationError,
)
from custom_components.bizneo_signin.const import SubmitResult


class FakeResponse:
    def __init__(self, status: int, headers=None) -> None:
        self.status = status
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def read(self):
        return b"{}"


class RaisingContext:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def __aenter__(self):
        raise self.error

    async def __aexit__(self, *args):
        return False


class FakeSession:
    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.responses.pop(0)


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_and_client_error(self):
        success = BizneoApiClient(
            FakeSession(FakeResponse(201)), "https://acme.test", "42", "secret"
        )
        result = await success.async_submit({"logged_time": {}})
        self.assertEqual(result.result, SubmitResult.OK)

        bad_request = BizneoApiClient(
            FakeSession(FakeResponse(400)), "https://acme.test", "42", "secret"
        )
        result = await bad_request.async_submit({"logged_time": {}})
        self.assertEqual(result.result, SubmitResult.ERROR)

    async def test_auth_and_not_found_have_specific_exceptions(self):
        with self.assertRaises(BizneoAuthError):
            await BizneoApiClient(
                FakeSession(FakeResponse(401)), "https://acme.test", "42", "secret"
            ).async_submit({})
        with self.assertRaises(BizneoConfigurationError):
            await BizneoApiClient(
                FakeSession(FakeResponse(404)), "https://acme.test", "42", "secret"
            ).async_submit({})

    async def test_503_is_retried_but_other_5xx_is_uncertain(self):
        session = FakeSession(FakeResponse(503), FakeResponse(201))
        with patch("custom_components.bizneo_signin.api.asyncio.sleep", new=AsyncMock()) as sleep:
            result = await BizneoApiClient(
                session, "https://acme.test", "42", "secret"
            ).async_submit({})
        self.assertEqual(result.result, SubmitResult.OK)
        self.assertEqual(len(session.calls), 2)
        sleep.assert_awaited_once()

        result = await BizneoApiClient(
            FakeSession(FakeResponse(500)), "https://acme.test", "42", "secret"
        ).async_submit({})
        self.assertEqual(result.result, SubmitResult.UNCERTAIN)

    async def test_429_is_retried_using_retry_after(self):
        session = FakeSession(FakeResponse(429, {"Retry-After": "1"}), FakeResponse(201))
        with patch("custom_components.bizneo_signin.api.asyncio.sleep", new=AsyncMock()) as sleep:
            result = await BizneoApiClient(
                session, "https://acme.test", "42", "secret"
            ).async_submit({})
        self.assertEqual(result.result, SubmitResult.OK)
        sleep.assert_awaited_once_with(1)

    async def test_timeout_and_disconnect_are_uncertain_and_not_retried(self):
        for error in (TimeoutError(), ServerDisconnectedError()):
            session = FakeSession(RaisingContext(error))
            result = await BizneoApiClient(
                session, "https://acme.test", "42", "secret"
            ).async_submit({})
            self.assertEqual(result.result, SubmitResult.UNCERTAIN)
            self.assertEqual(len(session.calls), 1)


if __name__ == "__main__":
    unittest.main()
