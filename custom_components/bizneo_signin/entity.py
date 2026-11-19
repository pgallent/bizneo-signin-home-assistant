"""Common entities for Bizneo Signin."""

from __future__ import annotations

from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DOMAIN, SIGNAL_UPDATE
from .manager import SigninManager


class SigninEntity(Entity):
    """Base push entity backed by a SigninManager."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: SigninManager, suffix: str) -> None:
        self.manager = manager
        self._attr_unique_id = f"{manager.entry.entry_id}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, manager.entry.entry_id)},
            name="Bizneo Signin",
            manufacturer="Bizneo",
            model="Jornada por geolocalización",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to manager pushes."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._handle_update)
        )

    def _handle_update(self, entry_id: str) -> None:
        if entry_id == self.manager.entry.entry_id:
            self.async_write_ha_state()
