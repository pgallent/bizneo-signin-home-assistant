"""Location-driven state machine for Bizneo Signin."""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.components.zone import in_zone
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .api import BizneoApiClient, BizneoAuthError, BizneoConfigurationError
from .const import (
    CONF_ENTRY_DWELL_MINUTES,
    CONF_ENTRY_WINDOW_END,
    CONF_ENTRY_WINDOW_START,
    CONF_EXIT_DWELL_MINUTES,
    CONF_TRACKED_ENTITY,
    CONF_WORK_ZONE,
    DOMAIN,
    EVENT_ERROR,
    EVENT_EXIT,
    EVENT_PAUSE,
    EVENT_STARTED,
    EVENT_SUBMITTED,
    SIGNAL_UPDATE,
    PauseType,
    SigninState,
    SubmitResult,
)
from .models import WorkSession
from .schedule import (
    ScheduleError,
    build_payload,
    complete_missing_pauses,
    create_pause,
    exit_window,
    in_time_window,
    is_working_day,
)
from .storage import SigninStorage


class SigninManager:
    """Coordinate geofencing, persisted timers, actions and submission."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: BizneoApiClient,
        storage: SigninStorage,
        *,
        rng: random.Random | random.SystemRandom | None = None,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self.storage = storage
        self.rng = rng or random.SystemRandom()
        self._inside: bool | None = None
        self._timer_task: asyncio.Task[None] | None = None
        self._submit_lock = asyncio.Lock()
        self._unsub_state = None

    @property
    def session(self) -> WorkSession:
        """Return the active persisted session."""
        return self.storage.session

    @property
    def options(self) -> dict[str, Any]:
        """Return entry options."""
        return dict(self.entry.options)

    async def async_start(self) -> None:
        """Load state, restore pending work and start location listeners."""
        await self.storage.async_load()
        tracker = self.hass.states.get(self.entry.data[CONF_TRACKED_ENTITY])
        self._inside = self._state_inside(tracker)
        self._unsub_state = async_track_state_change_event(
            self.hass,
            [self.entry.data[CONF_TRACKED_ENTITY], self.entry.data[CONF_WORK_ZONE]],
            self._async_state_changed,
        )

        if self.session.state is SigninState.SUBMITTING:
            self.session.state = SigninState.UNCERTAIN
            self.session.last_error = (
                "Home Assistant se reinició durante el envío; comprueba Bizneo"
            )
            await self.storage.async_save()
            self._notify(
                "envio_dudoso",
                "El reinicio ocurrió durante un envío. Comprueba Bizneo y usa "
                "resolver_envio_dudoso; no se reenviará automáticamente.",
            )
        elif self.session.state is SigninState.ENTRY_PENDING:
            if self._inside is True:
                self._restore_timer("entry")
            else:
                self.storage.session = WorkSession()
                await self.storage.async_save()
        elif self.session.state is SigninState.EXIT_PENDING:
            if self._inside is False:
                self._restore_timer("exit")
            else:
                self.session.state = SigninState.WORKING
                self.session.exit_pending_at = None
                await self.storage.async_save()
        elif self._inside and self.session.state in (
            SigninState.IDLE,
            SigninState.SUBMITTED,
        ):
            self._notify(
                "inicio_manual",
                "Home Assistant ha arrancado con la persona dentro de la zona. "
                "No se ha inferido una entrada; usa iniciar_jornada_manual si corresponde.",
            )
        elif self._inside is False and self.session.state is SigninState.WORKING:
            self._notify(
                "salida_manual",
                "Home Assistant ha arrancado con una jornada activa y la persona fuera "
                "de la zona. No se ha inferido la salida; usa finalizar_jornada_manual.",
            )
        self._signal_update()

    async def async_stop(self) -> None:
        """Unload listeners and timers."""
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        self._cancel_timer()

    @callback
    def _async_state_changed(self, event: Event) -> None:
        """Handle tracker or zone changes using zone geometry."""
        tracker = self.hass.states.get(self.entry.data[CONF_TRACKED_ENTITY])
        current = self._state_inside(tracker)
        if current is None or current == self._inside:
            return
        previous = self._inside
        self._inside = current
        crossed_at = dt_util.as_local(event.time_fired)
        if current and previous is False:
            self.hass.async_create_task(self._async_entered(crossed_at))
        elif not current and previous is True:
            self.hass.async_create_task(self._async_exited(crossed_at))

    def _state_inside(self, tracker: State | None) -> bool | None:
        zone = self.hass.states.get(self.entry.data[CONF_WORK_ZONE])
        if tracker is None or zone is None:
            return None
        if zone.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        latitude = tracker.attributes.get(ATTR_LATITUDE)
        longitude = tracker.attributes.get(ATTR_LONGITUDE)
        if latitude is None or longitude is None:
            return None
        radius = float(tracker.attributes.get("gps_accuracy", 0) or 0)
        try:
            return in_zone(zone, float(latitude), float(longitude), radius)
        except (KeyError, TypeError, ValueError):
            return None

    async def _async_entered(self, crossed_at: datetime) -> None:
        if self.session.state is SigninState.EXIT_PENDING:
            self._cancel_timer()
            self.session.state = SigninState.WORKING
            self.session.exit_pending_at = None
            await self.storage.async_save()
            self._signal_update()
            return
        if self.session.state not in (SigninState.IDLE, SigninState.SUBMITTED):
            return
        options = self.options
        try:
            if not is_working_day(crossed_at.date(), options):
                return
            if crossed_at.date().isoformat() in self.storage.sent_dates:
                return
            if not in_time_window(
                crossed_at,
                options[CONF_ENTRY_WINDOW_START],
                options[CONF_ENTRY_WINDOW_END],
            ):
                self._notify(
                    "entrada_fuera_ventana",
                    "Se detectó una entrada fuera de la ventana configurada. "
                    "Usa iniciar_jornada_manual si corresponde.",
                )
                return
        except ScheduleError as err:
            await self._async_error(str(err))
            return
        self.storage.session = WorkSession(
            state=SigninState.ENTRY_PENDING,
            entry_pending_at=crossed_at,
        )
        await self.storage.async_save()
        self._schedule_timer(
            "entry", crossed_at + timedelta(minutes=int(options[CONF_ENTRY_DWELL_MINUTES]))
        )
        self._signal_update()

    async def _async_exited(self, crossed_at: datetime) -> None:
        if self.session.state is SigninState.ENTRY_PENDING:
            self._cancel_timer()
            self.storage.session = WorkSession()
            await self.storage.async_save()
            self._signal_update()
            return
        if self.session.state is not SigninState.WORKING or not self.session.entry_at:
            return
        if crossed_at.date() != self.session.entry_at.date():
            self._notify(
                "salida_fuera_fecha",
                "La salida detectada no pertenece a la fecha de la jornada activa. "
                "Revisa la sesión y usa una acción manual.",
            )
            return
        try:
            start, end = exit_window(self.options, self.session.entry_at.date())
            if not in_time_window(crossed_at, start, end):
                self._notify(
                    "salida_fuera_ventana",
                    "Se detectó una salida fuera de la ventana configurada. La jornada "
                    "sigue activa y requiere finalizar_jornada_manual.",
                )
                return
        except ScheduleError as err:
            await self._async_error(str(err))
            return
        self.session.state = SigninState.EXIT_PENDING
        self.session.exit_pending_at = crossed_at
        await self.storage.async_save()
        self._schedule_timer(
            "exit",
            crossed_at + timedelta(minutes=int(self.options[CONF_EXIT_DWELL_MINUTES])),
        )
        self._signal_update()

    def _restore_timer(self, kind: str) -> None:
        crossed_at = (
            self.session.entry_pending_at if kind == "entry" else self.session.exit_pending_at
        )
        if crossed_at is None:
            return
        minutes = int(
            self.options[CONF_ENTRY_DWELL_MINUTES if kind == "entry" else CONF_EXIT_DWELL_MINUTES]
        )
        self._schedule_timer(kind, crossed_at + timedelta(minutes=minutes))

    def _schedule_timer(self, kind: str, target: datetime) -> None:
        self._cancel_timer()
        self._timer_task = self.hass.async_create_task(
            self._async_timer(kind, target), f"{DOMAIN}_{self.entry.entry_id}_{kind}"
        )

    async def _async_timer(self, kind: str, target: datetime) -> None:
        try:
            await asyncio.sleep(max(0.0, (target - dt_util.now()).total_seconds()))
            if kind == "entry":
                if self.session.state is SigninState.ENTRY_PENDING and self._inside:
                    await self._async_confirm_entry()
            elif self.session.state is SigninState.EXIT_PENDING and self._inside is False:
                await self._async_confirm_exit()
        except asyncio.CancelledError:
            return
        finally:
            if self._timer_task is asyncio.current_task():
                self._timer_task = None

    async def _async_confirm_entry(self) -> None:
        crossed_at = self.session.entry_pending_at
        if crossed_at is None:
            return
        self.session.state = SigninState.WORKING
        self.session.entry_at = crossed_at
        self.session.work_date = crossed_at.date().isoformat()
        self.session.entry_pending_at = None
        await self.storage.async_save()
        self._dismiss("inicio_manual")
        self._fire(EVENT_STARTED, {"date": self.session.work_date, "entry": crossed_at.isoformat()})
        self._signal_update()

    async def _async_confirm_exit(self) -> None:
        crossed_at = self.session.exit_pending_at
        if crossed_at is None:
            return
        self.session.exit_at = crossed_at
        self.session.exit_pending_at = None
        try:
            previous_kinds = {pause.kind for pause in self.session.pauses}
            self.session.pauses = complete_missing_pauses(self.session, self.options, self.rng)
            self.session.payload = build_payload(self.session, self.options)
        except ScheduleError as err:
            await self._async_error(str(err))
            return
        self._fire_generated_pause_events(previous_kinds)
        self._fire(EVENT_EXIT, {"date": self.session.work_date, "exit": crossed_at.isoformat()})
        await self._async_submit()

    async def async_register_pause(self, kind: PauseType, now: datetime | None = None) -> None:
        """Register a pause action at the real call time."""
        if self.session.state is not SigninState.WORKING:
            raise ScheduleError("No hay una jornada activa")
        moment = now or dt_util.now()
        pause = create_pause(self.session, kind, moment, self.options, self.rng)
        self.session.pauses.append(pause)
        self.session.pauses.sort(key=lambda item: item.start)
        await self.storage.async_save()
        self._fire(
            EVENT_PAUSE,
            {
                "date": self.session.work_date,
                "type": kind.value,
                "start": pause.start.isoformat(),
                "end": pause.end.isoformat(),
                "generated": False,
            },
        )
        self._signal_update()

    async def async_manual_start(self, moment: datetime | None = None) -> None:
        """Start a missed session explicitly."""
        if self.session.state not in (SigninState.IDLE, SigninState.SUBMITTED):
            raise ScheduleError("Ya existe una jornada activa o pendiente")
        started = moment or dt_util.now()
        if started > dt_util.now() + timedelta(seconds=1):
            raise ScheduleError("La entrada no puede estar en el futuro")
        if started.date().isoformat() in self.storage.sent_dates:
            raise ScheduleError("La jornada de esa fecha ya figura como enviada")
        if not is_working_day(started.date(), self.options):
            raise ScheduleError("La fecha no es laborable")
        self.storage.session = WorkSession(
            state=SigninState.WORKING,
            work_date=started.date().isoformat(),
            entry_at=started,
        )
        await self.storage.async_save()
        self._dismiss("inicio_manual")
        self._dismiss("entrada_fuera_ventana")
        self._fire(
            EVENT_STARTED,
            {"date": self.session.work_date, "entry": started.isoformat(), "manual": True},
        )
        self._signal_update()

    async def async_manual_finish(self, moment: datetime | None = None) -> None:
        """Finish an active session explicitly and submit it."""
        if self.session.state not in (SigninState.WORKING, SigninState.EXIT_PENDING):
            raise ScheduleError("No hay una jornada activa")
        finished = moment or dt_util.now()
        if not self.session.entry_at or finished <= self.session.entry_at:
            raise ScheduleError("La salida debe ser posterior a la entrada")
        if finished.date() != self.session.entry_at.date():
            raise ScheduleError("La entrada y la salida deben pertenecer al mismo día")
        self._cancel_timer()
        previous_exit = self.session.exit_at
        previous_pending = self.session.exit_pending_at
        self.session.exit_at = finished
        self.session.exit_pending_at = None
        try:
            previous_kinds = {pause.kind for pause in self.session.pauses}
            pauses = complete_missing_pauses(self.session, self.options, self.rng)
            self.session.pauses = pauses
            self.session.payload = build_payload(self.session, self.options)
        except ScheduleError:
            self.session.exit_at = previous_exit
            self.session.exit_pending_at = previous_pending
            raise
        self._fire_generated_pause_events(previous_kinds)
        self._dismiss("salida_fuera_ventana")
        self._dismiss("salida_fuera_fecha")
        self._fire(
            EVENT_EXIT,
            {"date": self.session.work_date, "exit": finished.isoformat(), "manual": True},
        )
        await self._async_submit()

    async def _async_submit(self, *, explicit_retry: bool = False) -> None:
        async with self._submit_lock:
            eligible = {SigninState.WORKING, SigninState.EXIT_PENDING}
            if explicit_retry:
                eligible.add(SigninState.FAILED)
            if not self.session.payload or self.session.state not in eligible:
                return
            self.session.state = SigninState.SUBMITTING
            self.session.last_error = None
            await self.storage.async_save()
            self._signal_update()
            try:
                result = await self.client.async_submit(self.session.payload)
            except BizneoAuthError as err:
                self.session.state = SigninState.FAILED
                self.session.last_error = str(err)
                await self.storage.async_save()
                self.entry.async_start_reauth(self.hass)
                self._notify(
                    "reautenticacion", "Bizneo rechazó el token. Reautentica la integración."
                )
                self._fire(
                    EVENT_ERROR, {"date": self.session.work_date, "reason": "authentication"}
                )
                self._signal_update()
                return
            except BizneoConfigurationError as err:
                await self._async_error(str(err))
                self._notify("configuracion", "Revisa el dominio de Bizneo y el ID de usuario.")
                return
            if result.result is SubmitResult.OK:
                await self._async_mark_submitted()
            elif result.result is SubmitResult.UNCERTAIN:
                self.session.state = SigninState.UNCERTAIN
                self.session.last_error = result.message
                await self.storage.async_save()
                self._notify(
                    "envio_dudoso",
                    "No se sabe si Bizneo creó la jornada. Compruébalo y usa "
                    "resolver_envio_dudoso; no se reenviará automáticamente.",
                )
                self._fire(EVENT_ERROR, {"date": self.session.work_date, "reason": "uncertain"})
                self._signal_update()
            else:
                await self._async_error(result.message)

    async def _async_mark_submitted(self) -> None:
        work_date = self.session.work_date
        if work_date is None:
            return
        summary = {
            "date": work_date,
            "entry": self.session.entry_at.isoformat() if self.session.entry_at else None,
            "exit": self.session.exit_at.isoformat() if self.session.exit_at else None,
            "pauses": [pause.to_dict() for pause in self.session.pauses],
            "submitted_at": dt_util.now().isoformat(),
        }
        self.storage.sent_dates[work_date] = {"submitted_at": summary["submitted_at"]}
        self.storage.last_workday = summary
        self.session.state = SigninState.SUBMITTED
        self.session.last_error = None
        self.session.payload = None
        await self.storage.async_save()
        self._dismiss("envio_dudoso")
        self._fire(EVENT_SUBMITTED, {"date": work_date})
        self._signal_update()

    async def async_retry(self) -> None:
        """Retry only a definitely failed submission."""
        if self.session.state is not SigninState.FAILED or not self.session.payload:
            raise ScheduleError("No hay un envío fallido que se pueda reintentar")
        await self._async_submit(explicit_retry=True)

    async def async_resolve_uncertain(self, created: bool) -> None:
        """Resolve an uncertain result after the user checks Bizneo."""
        if self.session.state is not SigninState.UNCERTAIN:
            raise ScheduleError("No hay un envío dudoso pendiente")
        if created:
            await self._async_mark_submitted()
            return
        self.session.state = SigninState.FAILED
        self.session.last_error = "El usuario confirmó que Bizneo no creó la jornada"
        await self.storage.async_save()
        self._dismiss("envio_dudoso")
        self._signal_update()

    async def async_discard(self) -> None:
        """Discard the current local session without touching Bizneo."""
        self._cancel_timer()
        self.storage.session = WorkSession()
        await self.storage.async_save()
        for suffix in (
            "inicio_manual",
            "salida_manual",
            "salida_fuera_ventana",
            "salida_fuera_fecha",
            "envio_dudoso",
        ):
            self._dismiss(suffix)
        self._signal_update()

    async def _async_error(self, message: str) -> None:
        self.session.state = SigninState.FAILED
        self.session.last_error = message
        await self.storage.async_save()
        self._fire(EVENT_ERROR, {"date": self.session.work_date, "reason": message})
        self._signal_update()

    def _fire(self, event_type: str, data: dict[str, Any]) -> None:
        self.hass.bus.async_fire(event_type, {"entry_id": self.entry.entry_id, **data})

    def _fire_generated_pause_events(self, previous_kinds: set[PauseType]) -> None:
        for pause in self.session.pauses:
            if not pause.generated or pause.kind in previous_kinds:
                continue
            self._fire(
                EVENT_PAUSE,
                {
                    "date": self.session.work_date,
                    "type": pause.kind.value,
                    "start": pause.start.isoformat(),
                    "end": pause.end.isoformat(),
                    "generated": True,
                },
            )

    def _signal_update(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE, self.entry.entry_id)

    def _notification_id(self, suffix: str) -> str:
        return f"{DOMAIN}_{self.entry.entry_id}_{suffix}"

    def _notify(self, suffix: str, message: str) -> None:
        persistent_notification.async_create(
            self.hass,
            message,
            title="Bizneo Signin",
            notification_id=self._notification_id(suffix),
        )

    def _dismiss(self, suffix: str) -> None:
        persistent_notification.async_dismiss(self.hass, self._notification_id(suffix))

    def _cancel_timer(self) -> None:
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        self._timer_task = None
