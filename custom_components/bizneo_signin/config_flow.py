"""UI configuration flows for Bizneo Signin."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector

from .const import (
    COMMUNITY_CODES,
    COMMUNITY_NONE,
    CONF_BIZNEO_DOMAIN,
    CONF_COMMUNITY,
    CONF_ENTRY_DWELL_MINUTES,
    CONF_ENTRY_WINDOW_END,
    CONF_ENTRY_WINDOW_START,
    CONF_EXIT_DWELL_MINUTES,
    CONF_EXIT_WINDOW_END,
    CONF_EXIT_WINDOW_START,
    CONF_FRIDAY_EXIT_WINDOW_END,
    CONF_FRIDAY_EXIT_WINDOW_START,
    CONF_LONG_PAUSE_MAX_MINUTES,
    CONF_LONG_PAUSE_MIN_MINUTES,
    CONF_LONG_PAUSE_WINDOW_END,
    CONF_LONG_PAUSE_WINDOW_START,
    CONF_LONG_REST_ID,
    CONF_NON_WORKING_DATES,
    CONF_PAUSES_AS_REST,
    CONF_RANDOM_STEP_MINUTES,
    CONF_RANDOMIZE_PAUSE_DURATIONS,
    CONF_SHORT_PAUSE_MAX_MINUTES,
    CONF_SHORT_PAUSE_MIN_MINUTES,
    CONF_SHORT_PAUSE_WINDOW_END,
    CONF_SHORT_PAUSE_WINDOW_START,
    CONF_SHORT_REST_ID,
    CONF_TRACKED_ENTITY,
    CONF_USER_ID,
    CONF_WORK_ZONE,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from .schedule import ScheduleError, parse_non_working_dates, parse_time


def _validate_domain(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path:
        raise vol.Invalid("invalid_domain")
    return value


# Form schemas are serialized for the frontend, so field validators must be types,
# selectors or voluptuous built-ins. Custom checks (domain, times) run inside the steps.
def _account_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_BIZNEO_DOMAIN,
                default=defaults.get(CONF_BIZNEO_DOMAIN, "https://empresa.bizneohr.com"),
            ): cv.string,
            vol.Required(CONF_USER_ID, default=defaults.get(CONF_USER_ID, "")): vol.All(
                cv.string, vol.Length(min=1)
            ),
            vol.Required(CONF_TOKEN, default=defaults.get(CONF_TOKEN, "")): vol.All(
                selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Length(min=1),
            ),
        }
    )


def _tracking_schema(defaults: dict[str, Any]) -> vol.Schema:
    tracked_key = (
        vol.Required(CONF_TRACKED_ENTITY, default=defaults[CONF_TRACKED_ENTITY])
        if CONF_TRACKED_ENTITY in defaults
        else vol.Required(CONF_TRACKED_ENTITY)
    )
    zone_key = (
        vol.Required(CONF_WORK_ZONE, default=defaults[CONF_WORK_ZONE])
        if CONF_WORK_ZONE in defaults
        else vol.Required(CONF_WORK_ZONE)
    )
    return vol.Schema(
        {
            tracked_key: selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["person", "device_tracker"])
            ),
            zone_key: selector.EntitySelector(selector.EntitySelectorConfig(domain="zone")),
        }
    )


def _options_schema(defaults: dict[str, Any]) -> vol.Schema:
    values = {**DEFAULT_OPTIONS, **defaults}
    time_fields = (
        CONF_ENTRY_WINDOW_START,
        CONF_ENTRY_WINDOW_END,
        CONF_EXIT_WINDOW_START,
        CONF_EXIT_WINDOW_END,
        CONF_FRIDAY_EXIT_WINDOW_START,
        CONF_FRIDAY_EXIT_WINDOW_END,
        CONF_SHORT_PAUSE_WINDOW_START,
        CONF_SHORT_PAUSE_WINDOW_END,
        CONF_LONG_PAUSE_WINDOW_START,
        CONF_LONG_PAUSE_WINDOW_END,
    )
    schema: dict[Any, Any] = {
        vol.Required(key, default=values[key]): cv.string for key in time_fields
    }
    schema.update(
        {
            vol.Required(
                CONF_ENTRY_DWELL_MINUTES, default=values[CONF_ENTRY_DWELL_MINUTES]
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
            vol.Required(CONF_EXIT_DWELL_MINUTES, default=values[CONF_EXIT_DWELL_MINUTES]): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=60)
            ),
            vol.Required(
                CONF_SHORT_PAUSE_MIN_MINUTES, default=values[CONF_SHORT_PAUSE_MIN_MINUTES]
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=180)),
            vol.Required(
                CONF_SHORT_PAUSE_MAX_MINUTES, default=values[CONF_SHORT_PAUSE_MAX_MINUTES]
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=180)),
            vol.Required(
                CONF_LONG_PAUSE_MIN_MINUTES, default=values[CONF_LONG_PAUSE_MIN_MINUTES]
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=180)),
            vol.Required(
                CONF_LONG_PAUSE_MAX_MINUTES, default=values[CONF_LONG_PAUSE_MAX_MINUTES]
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=180)),
            vol.Required(
                CONF_RANDOMIZE_PAUSE_DURATIONS, default=values[CONF_RANDOMIZE_PAUSE_DURATIONS]
            ): cv.boolean,
            vol.Required(
                CONF_RANDOM_STEP_MINUTES, default=values[CONF_RANDOM_STEP_MINUTES]
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
            # Entries created before COMMUNITY_NONE existed store "" for "no community".
            vol.Required(
                CONF_COMMUNITY, default=values[CONF_COMMUNITY] or COMMUNITY_NONE
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[COMMUNITY_NONE, *COMMUNITY_CODES],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key=CONF_COMMUNITY,
                )
            ),
            vol.Optional(CONF_NON_WORKING_DATES, default=values[CONF_NON_WORKING_DATES]): cv.string,
            vol.Required(CONF_PAUSES_AS_REST, default=values[CONF_PAUSES_AS_REST]): cv.boolean,
            vol.Optional(CONF_SHORT_REST_ID, default=values[CONF_SHORT_REST_ID]): vol.All(
                vol.Coerce(int), vol.Range(min=0)
            ),
            vol.Optional(CONF_LONG_REST_ID, default=values[CONF_LONG_REST_ID]): vol.All(
                vol.Coerce(int), vol.Range(min=0)
            ),
        }
    )
    return vol.Schema(schema)


def _validate_options(values: dict[str, Any]) -> None:
    pairs = (
        (CONF_ENTRY_WINDOW_START, CONF_ENTRY_WINDOW_END),
        (CONF_EXIT_WINDOW_START, CONF_EXIT_WINDOW_END),
        (CONF_FRIDAY_EXIT_WINDOW_START, CONF_FRIDAY_EXIT_WINDOW_END),
        (CONF_SHORT_PAUSE_WINDOW_START, CONF_SHORT_PAUSE_WINDOW_END),
        (CONF_LONG_PAUSE_WINDOW_START, CONF_LONG_PAUSE_WINDOW_END),
    )
    for start, end in pairs:
        if parse_time(values[end]) < parse_time(values[start]):
            raise ScheduleError("reversed_window")
    if values[CONF_SHORT_PAUSE_MAX_MINUTES] < values[CONF_SHORT_PAUSE_MIN_MINUTES]:
        raise ScheduleError("invalid_pause_range")
    if values[CONF_LONG_PAUSE_MAX_MINUTES] < values[CONF_LONG_PAUSE_MIN_MINUTES]:
        raise ScheduleError("invalid_pause_range")
    parse_non_working_dates(values.get(CONF_NON_WORKING_DATES, ""))
    if values[CONF_PAUSES_AS_REST] and (
        values.get(CONF_SHORT_REST_ID, 0) <= 0 or values.get(CONF_LONG_REST_ID, 0) <= 0
    ):
        raise ScheduleError("missing_rest_ids")


class BizneoSigninConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a Bizneo Signin account."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                user_input[CONF_BIZNEO_DOMAIN] = _validate_domain(user_input[CONF_BIZNEO_DOMAIN])
            except vol.Invalid:
                errors[CONF_BIZNEO_DOMAIN] = "invalid_domain"
            if not errors:
                self._data.update(user_input)
                await self.async_set_unique_id(
                    f"{user_input[CONF_BIZNEO_DOMAIN]}|{user_input[CONF_USER_ID]}"
                )
                self._abort_if_unique_id_configured()
                return await self.async_step_tracking()
        return self.async_show_form(
            step_id="user", data_schema=_account_schema(user_input or {}), errors=errors
        )

    async def async_step_tracking(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_schedule()
        return self.async_show_form(step_id="tracking", data_schema=_tracking_schema({}))

    async def async_step_schedule(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                _validate_options(user_input)
            except (ScheduleError, ValueError):
                errors["base"] = "invalid_schedule"
            if not errors:
                data = {
                    key: self._data[key]
                    for key in (
                        CONF_BIZNEO_DOMAIN,
                        CONF_USER_ID,
                        CONF_TOKEN,
                        CONF_TRACKED_ENTITY,
                        CONF_WORK_ZONE,
                    )
                }
                return self.async_create_entry(
                    title=f"Bizneo · {self._data[CONF_USER_ID]}",
                    data=data,
                    options=user_input,
                )
        return self.async_show_form(
            step_id="schedule",
            data_schema=_options_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        self._reauth_entry = self._get_reauth_entry()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            token = str(user_input[CONF_TOKEN]).strip()
            if not token:
                errors[CONF_TOKEN] = "invalid_auth"
            else:
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data_updates={CONF_TOKEN: token},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        defaults = dict(entry.data)
        if user_input is not None:
            try:
                user_input[CONF_BIZNEO_DOMAIN] = _validate_domain(user_input[CONF_BIZNEO_DOMAIN])
            except vol.Invalid:
                errors[CONF_BIZNEO_DOMAIN] = "invalid_domain"
            if not errors:
                new_unique_id = f"{user_input[CONF_BIZNEO_DOMAIN]}|{user_input[CONF_USER_ID]}"
                existing = self.hass.config_entries.async_entry_for_domain_unique_id(
                    DOMAIN, new_unique_id
                )
                if existing is not None and existing.entry_id != entry.entry_id:
                    return self.async_abort(reason="already_configured")
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=new_unique_id,
                    data_updates=user_input,
                )
        schema = _account_schema(defaults).extend(_tracking_schema(defaults).schema)
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> BizneoSigninOptionsFlow:
        return BizneoSigninOptionsFlow(config_entry)


class BizneoSigninOptionsFlow(config_entries.OptionsFlow):
    """Edit schedule behavior without exposing credentials."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                _validate_options(user_input)
            except (ScheduleError, ValueError):
                errors["base"] = "invalid_schedule"
            if not errors:
                return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(user_input or dict(self._entry.options)),
            errors=errors,
        )
