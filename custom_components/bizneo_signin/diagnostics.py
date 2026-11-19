"""Privacy-safe diagnostics for Bizneo Signin."""

from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BIZNEO_DOMAIN,
    CONF_LONG_REST_ID,
    CONF_NON_WORKING_DATES,
    CONF_SHORT_REST_ID,
    CONF_TOKEN,
    CONF_TRACKED_ENTITY,
    CONF_USER_ID,
    CONF_WORK_ZONE,
    DOMAIN,
)

TO_REDACT_CONFIG = {
    CONF_BIZNEO_DOMAIN,
    CONF_TOKEN,
    CONF_USER_ID,
    CONF_TRACKED_ENTITY,
    CONF_WORK_ZONE,
}
TO_REDACT_OPTIONS = {
    CONF_NON_WORKING_DATES,
    CONF_SHORT_REST_ID,
    CONF_LONG_REST_ID,
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Return diagnostics without credentials, IDs, coordinates or payloads."""
    manager = hass.data[DOMAIN][entry.entry_id]
    return {
        "config": async_redact_data(dict(entry.data), TO_REDACT_CONFIG),
        "options": async_redact_data(dict(entry.options), TO_REDACT_OPTIONS),
        "state": manager.session.state.value,
        "pause_types": [pause.kind.value for pause in manager.session.pauses],
        "sent_date_count": len(manager.storage.sent_dates),
        "has_pending_payload": manager.session.payload is not None,
    }
