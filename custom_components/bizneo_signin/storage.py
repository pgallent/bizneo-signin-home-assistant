"""Versioned Home Assistant storage for Bizneo Signin."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION
from .models import WorkSession


class SigninStorage:
    """Persist sessions and de-duplication data atomically."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}",
            private=True,
            atomic_writes=True,
        )
        self.session = WorkSession()
        self.sent_dates: dict[str, dict[str, Any]] = {}
        self.last_workday: dict[str, Any] | None = None

    async def async_load(self) -> None:
        """Load persisted state."""
        data = await self._store.async_load() or {}
        self.session = WorkSession.from_dict(data.get("session"))
        self.sent_dates = dict(data.get("sent_dates", {}))
        self.last_workday = data.get("last_workday")

    async def async_save(self) -> None:
        """Persist all state immediately."""
        await self._store.async_save(
            {
                "session": self.session.to_dict(),
                "sent_dates": self.sent_dates,
                "last_workday": self.last_workday,
            }
        )

    async def async_remove(self) -> None:
        """Remove all persisted personal state for a deleted config entry."""
        await self._store.async_remove()
