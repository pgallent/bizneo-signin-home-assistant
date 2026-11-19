"""Bizneo Signin status sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import SigninEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SigninStatusSensor(manager), LastWorkdaySensor(manager)])


class SigninStatusSensor(SigninEntity, SensorEntity):
    """Current state machine state and safe context."""

    _attr_translation_key = "jornada_estado"
    _attr_icon = "mdi:timeline-clock"

    def __init__(self, manager) -> None:
        super().__init__(manager, "status")

    @property
    def native_value(self) -> str:
        return self.manager.session.state.value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        session = self.manager.session
        return {
            "fecha": session.work_date,
            "entrada": session.entry_at.isoformat() if session.entry_at else None,
            "entrada_pendiente": (
                session.entry_pending_at.isoformat() if session.entry_pending_at else None
            ),
            "salida_pendiente": (
                session.exit_pending_at.isoformat() if session.exit_pending_at else None
            ),
            "pausas": [pause.to_dict() for pause in session.pauses],
            "ultimo_error": session.last_error,
        }


class LastWorkdaySensor(SigninEntity, SensorEntity):
    """Last successfully submitted workday."""

    _attr_translation_key = "ultima_jornada"
    _attr_icon = "mdi:calendar-check"

    def __init__(self, manager) -> None:
        super().__init__(manager, "last_workday")

    @property
    def native_value(self) -> str | None:
        last = self.manager.storage.last_workday
        return last.get("date") if last else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return dict(self.manager.storage.last_workday or {})
