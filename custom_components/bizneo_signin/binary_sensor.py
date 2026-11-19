"""Bizneo Signin active-session binary sensor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, SigninState
from .entity import SigninEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([SigninActiveSensor(hass.data[DOMAIN][entry.entry_id])])


class SigninActiveSensor(SigninEntity, BinarySensorEntity):
    """Whether a session still needs attention."""

    _attr_translation_key = "jornada_activa"
    _attr_icon = "mdi:briefcase-clock"

    def __init__(self, manager) -> None:
        super().__init__(manager, "active")

    @property
    def is_on(self) -> bool:
        return self.manager.session.state in {
            SigninState.WORKING,
            SigninState.EXIT_PENDING,
            SigninState.SUBMITTING,
            SigninState.FAILED,
            SigninState.UNCERTAIN,
        }
