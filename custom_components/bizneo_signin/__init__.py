"""Bizneo Signin integration."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register integration actions once."""
    import voluptuous as vol
    from homeassistant.core import ServiceCall
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.util import dt as dt_util

    from .const import (
        SERVICE_DISCARD,
        SERVICE_MANUAL_FINISH,
        SERVICE_MANUAL_START,
        SERVICE_REGISTER_PAUSE,
        SERVICE_RESOLVE_UNCERTAIN,
        SERVICE_RETRY,
        PauseType,
    )
    from .manager import SigninManager
    from .schedule import ScheduleError

    hass.data.setdefault(DOMAIN, {})

    def manager_for(call: ServiceCall) -> SigninManager:
        entry_id = call.data.get("config_entry_id")
        managers = hass.data[DOMAIN]
        if entry_id:
            manager = managers.get(entry_id)
            if manager is None:
                raise HomeAssistantError("La configuración indicada no está cargada")
            return manager
        if len(managers) != 1:
            raise HomeAssistantError("Indica config_entry_id cuando hay varias configuraciones")
        return next(iter(managers.values()))

    def parse_moment(value: str | None) -> datetime | None:
        if not value:
            return None
        parsed = dt_util.parse_datetime(value)
        if parsed is None:
            raise HomeAssistantError("La fecha y hora no son válidas")
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        return dt_util.as_local(parsed)

    async def handle(call: ServiceCall) -> None:
        manager = manager_for(call)
        try:
            if call.service == SERVICE_REGISTER_PAUSE:
                await manager.async_register_pause(PauseType(call.data["tipo"]))
            elif call.service == SERVICE_MANUAL_START:
                await manager.async_manual_start(parse_moment(call.data.get("hora")))
            elif call.service == SERVICE_MANUAL_FINISH:
                await manager.async_manual_finish(parse_moment(call.data.get("hora")))
            elif call.service == SERVICE_DISCARD:
                await manager.async_discard()
            elif call.service == SERVICE_RETRY:
                await manager.async_retry()
            elif call.service == SERVICE_RESOLVE_UNCERTAIN:
                await manager.async_resolve_uncertain(call.data["resultado"] == "creado")
        except ScheduleError as err:
            raise HomeAssistantError(str(err)) from err

    common = {vol.Optional("config_entry_id"): str}
    schemas = {
        SERVICE_REGISTER_PAUSE: vol.Schema(
            {**common, vol.Required("tipo"): vol.In(["corta", "larga"])}
        ),
        SERVICE_MANUAL_START: vol.Schema({**common, vol.Optional("hora"): str}),
        SERVICE_MANUAL_FINISH: vol.Schema({**common, vol.Optional("hora"): str}),
        SERVICE_DISCARD: vol.Schema(common),
        SERVICE_RETRY: vol.Schema(common),
        SERVICE_RESOLVE_UNCERTAIN: vol.Schema(
            {**common, vol.Required("resultado"): vol.In(["creado", "no_creado"])}
        ),
    }
    for service, schema in schemas.items():
        hass.services.async_register(DOMAIN, service, handle, schema=schema)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Bizneo Signin config entry."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .api import BizneoApiClient
    from .const import (
        CONF_BIZNEO_DOMAIN,
        CONF_TOKEN,
        CONF_USER_ID,
        PLATFORMS,
    )
    from .manager import SigninManager
    from .storage import SigninStorage

    client = BizneoApiClient(
        async_get_clientsession(hass),
        entry.data[CONF_BIZNEO_DOMAIN],
        entry.data[CONF_USER_ID],
        entry.data[CONF_TOKEN],
    )
    manager = SigninManager(hass, entry, client, SigninStorage(hass, entry.entry_id))
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    await manager.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and all listeners."""
    from .const import PLATFORMS

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        manager = hass.data[DOMAIN].pop(entry.entry_id)
        await manager.async_stop()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove persisted state when the user deletes the config entry."""
    from .storage import SigninStorage

    await SigninStorage(hass, entry.entry_id).async_remove()


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
