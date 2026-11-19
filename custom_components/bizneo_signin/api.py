"""Asynchronous Bizneo write-only API client."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from aiohttp import (
    ClientConnectionError,
    ClientConnectorError,
    ClientError,
    ClientResponseError,
    ClientSession,
)

from .const import SubmitResult


class BizneoAuthError(Exception):
    """Bizneo rejected the token."""


class BizneoConfigurationError(Exception):
    """Bizneo domain or user ID is invalid."""


@dataclass(slots=True)
class ApiResult:
    """Safe API result without credentials or personal data."""

    result: SubmitResult
    message: str
    status: int | None = None


class BizneoApiClient:
    """Submit full workdays to Bizneo using Home Assistant's web session."""

    def __init__(
        self,
        session: ClientSession,
        domain: str,
        user_id: str,
        token: str,
        *,
        retries: int = 3,
    ) -> None:
        self._session = session
        self._domain = domain.rstrip("/")
        self._user_id = user_id
        self._token = token
        self._retries = retries

    async def async_submit(self, payload: dict[str, Any]) -> ApiResult:
        """Submit once, retrying only errors known not to have been accepted."""
        url = f"{self._domain}/api/v1/users/{quote(self._user_id, safe='')}/logged-times"
        for attempt in range(self._retries + 1):
            try:
                async with self._session.post(
                    url,
                    params={"token": self._token},
                    json=payload,
                    headers={"Accept": "application/json"},
                    timeout=30,
                ) as response:
                    status = response.status
                    if 200 <= status < 300:
                        await response.read()
                        return ApiResult(SubmitResult.OK, "Jornada registrada", status)
                    if status in (401, 403):
                        raise BizneoAuthError("Bizneo rechazó las credenciales")
                    if status == 404:
                        raise BizneoConfigurationError("Bizneo no encuentra el usuario o la ruta")
                    if status in (429, 503) and attempt < self._retries:
                        await response.read()
                        retry_after = response.headers.get("Retry-After", "")
                        delay = (
                            min(int(retry_after), 60)
                            if retry_after.isdigit()
                            else 2 ** (attempt + 1)
                        )
                        await asyncio.sleep(delay)
                        continue
                    if status >= 500:
                        await response.read()
                        return ApiResult(
                            SubmitResult.UNCERTAIN,
                            f"Respuesta dudosa de Bizneo (HTTP {status})",
                            status,
                        )
                    await response.read()
                    return ApiResult(SubmitResult.ERROR, f"Bizneo respondió HTTP {status}", status)
            except (BizneoAuthError, BizneoConfigurationError):
                raise
            except TimeoutError:
                return ApiResult(
                    SubmitResult.UNCERTAIN,
                    "Bizneo no respondió a tiempo; comprueba la jornada antes de reenviar",
                )
            except ClientConnectorError:
                # Connection establishment failures have no response and are safe to retry.
                if attempt < self._retries:
                    await asyncio.sleep(2 ** (attempt + 1))
                    continue
                return ApiResult(SubmitResult.ERROR, "No se pudo conectar con Bizneo")
            except (ClientConnectionError, ClientResponseError, ClientError):
                # Any failure after a request may have reached the server is uncertain.
                return ApiResult(
                    SubmitResult.UNCERTAIN,
                    "La conexión se cortó durante la respuesta; comprueba Bizneo",
                )
        return ApiResult(SubmitResult.ERROR, "Bizneo sigue pidiendo esperar")
