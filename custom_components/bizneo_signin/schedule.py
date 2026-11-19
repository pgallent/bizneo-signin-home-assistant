"""Deterministic scheduling and Bizneo payload construction."""

from __future__ import annotations

import random
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from typing import Any

import holidays

from .const import (
    CONF_COMMUNITY,
    CONF_FRIDAY_EXIT_WINDOW_END,
    CONF_FRIDAY_EXIT_WINDOW_START,
    CONF_LONG_PAUSE_WINDOW_END,
    CONF_LONG_PAUSE_WINDOW_START,
    CONF_LONG_REST_ID,
    CONF_NON_WORKING_DATES,
    CONF_PAUSES_AS_REST,
    CONF_RANDOM_STEP_MINUTES,
    CONF_RANDOMIZE_PAUSE_DURATIONS,
    CONF_SHORT_PAUSE_WINDOW_END,
    CONF_SHORT_PAUSE_WINDOW_START,
    CONF_SHORT_REST_ID,
    PauseType,
)
from .models import Pause, WorkSession

COMMUNITY_CODES = {
    "AN",
    "AR",
    "AS",
    "IB",
    "CN",
    "CB",
    "CM",
    "CL",
    "CT",
    "CE",
    "EX",
    "GA",
    "RI",
    "MD",
    "ML",
    "MC",
    "NC",
    "PV",
    "VC",
}


class ScheduleError(ValueError):
    """Invalid schedule or action."""


def parse_time(value: str) -> time:
    """Parse strict HH:MM values."""
    try:
        parsed = time.fromisoformat(value)
    except (TypeError, ValueError) as err:
        raise ScheduleError(f"Hora no válida: {value!r}") from err
    if parsed.second or parsed.microsecond:
        raise ScheduleError(f"La hora debe usar HH:MM: {value!r}")
    return parsed


def in_time_window(moment: datetime, start: str, end: str) -> bool:
    """Return whether a local datetime is inside an inclusive same-day window."""
    start_time, end_time = parse_time(start), parse_time(end)
    if end_time < start_time:
        raise ScheduleError("La ventana horaria está al revés")
    return start_time <= moment.timetz().replace(tzinfo=None) <= end_time


def exit_window(options: Mapping[str, Any], work_date: date) -> tuple[str, str]:
    """Return the regular or Friday exit window."""
    if work_date.weekday() == 4:
        return (
            str(options[CONF_FRIDAY_EXIT_WINDOW_START]),
            str(options[CONF_FRIDAY_EXIT_WINDOW_END]),
        )
    return str(options["exit_window_start"]), str(options["exit_window_end"])


def parse_non_working_dates(value: str | list[str]) -> set[date]:
    """Parse comma/newline-separated dates and inclusive ranges."""
    items = value if isinstance(value, list) else value.replace("\n", ",").split(",")
    result: set[date] = set()
    for raw in items:
        item = str(raw).strip()
        if not item:
            continue
        try:
            if ".." not in item:
                result.add(date.fromisoformat(item))
                continue
            start, end = (date.fromisoformat(part.strip()) for part in item.split("..", 1))
        except ValueError as err:
            raise ScheduleError(f"Fecha no válida: {item!r}") from err
        if end < start:
            raise ScheduleError(f"Rango de fechas al revés: {item}")
        if (end - start).days > 366:
            raise ScheduleError("Un rango no laborable no puede superar un año")
        result.update(start + timedelta(days=offset) for offset in range((end - start).days + 1))
    return result


def is_working_day(day: date, options: Mapping[str, Any], holidays_module=None) -> bool:
    """Return whether a date is eligible for automatic tracking."""
    if day.weekday() >= 5:
        return False
    if day in parse_non_working_dates(options.get(CONF_NON_WORKING_DATES, "")):
        return False
    community = str(options.get(CONF_COMMUNITY, "")).strip().upper()
    if not community:
        return True
    if community not in COMMUNITY_CODES:
        raise ScheduleError(f"Código de comunidad autónoma no válido: {community}")
    if holidays_module is None:
        holidays_module = holidays
    return day not in holidays_module.Spain(subdiv=community, years=[day.year])


def choose_duration(
    kind: PauseType,
    options: Mapping[str, Any],
    rng: random.Random | random.SystemRandom,
) -> int:
    """Choose a fixed or stepped random pause duration."""
    prefix = "short" if kind is PauseType.SHORT else "long"
    low = int(options[f"{prefix}_pause_min_minutes"])
    high = int(options[f"{prefix}_pause_max_minutes"])
    if low <= 0 or high < low:
        raise ScheduleError("El rango de duración de pausa no es válido")
    if not options.get(CONF_RANDOMIZE_PAUSE_DURATIONS) or low == high:
        return low
    step = int(options.get(CONF_RANDOM_STEP_MINUTES, 1))
    if step <= 0:
        raise ScheduleError("El paso aleatorio debe ser mayor que cero")
    values = list(range(low, high + 1, step))
    if values[-1] != high:
        values.append(high)
    return rng.choice(values)


def pause_window(kind: PauseType, options: Mapping[str, Any]) -> tuple[str, str]:
    """Return a pause window."""
    if kind is PauseType.SHORT:
        return (
            str(options[CONF_SHORT_PAUSE_WINDOW_START]),
            str(options[CONF_SHORT_PAUSE_WINDOW_END]),
        )
    return (
        str(options[CONF_LONG_PAUSE_WINDOW_START]),
        str(options[CONF_LONG_PAUSE_WINDOW_END]),
    )


def create_pause(
    session: WorkSession,
    kind: PauseType,
    start: datetime,
    options: Mapping[str, Any],
    rng: random.Random | random.SystemRandom,
    *,
    generated: bool = False,
) -> Pause:
    """Validate and create a pause using the real supplied start time."""
    if session.entry_at is None:
        raise ScheduleError("No hay una jornada activa")
    if start.date() != session.entry_at.date():
        raise ScheduleError("La pausa debe pertenecer a la fecha de la jornada")
    if any(item.kind is kind for item in session.pauses):
        raise ScheduleError(f"La pausa {kind.value} ya está registrada")
    if kind is PauseType.SHORT and session.entry_at.weekday() == 4:
        raise ScheduleError("Los viernes no requieren pausa corta")
    start_window, end_window = pause_window(kind, options)
    if not in_time_window(start, start_window, end_window):
        raise ScheduleError(f"La pausa {kind.value} está fuera de su ventana")
    duration = choose_duration(kind, options, rng)
    pause = Pause(kind, start, start + timedelta(minutes=duration), generated)
    if pause.start <= session.entry_at:
        raise ScheduleError("La pausa debe ser posterior a la entrada")
    if session.exit_at and pause.end >= session.exit_at:
        raise ScheduleError("La pausa debe terminar antes de la salida")
    if any(pause.start < other.end and other.start < pause.end for other in session.pauses):
        raise ScheduleError("La pausa se solapa con otra pausa")
    return pause


def complete_missing_pauses(
    session: WorkSession,
    options: Mapping[str, Any],
    rng: random.Random | random.SystemRandom,
) -> list[Pause]:
    """Generate any required pauses that were not registered."""
    if session.entry_at is None or session.exit_at is None:
        raise ScheduleError("La jornada necesita entrada y salida")
    required = (
        [PauseType.LONG] if session.entry_at.weekday() == 4 else [PauseType.SHORT, PauseType.LONG]
    )
    pauses = list(session.pauses)
    for kind in required:
        if any(pause.kind is kind for pause in pauses):
            continue
        start_text, end_text = pause_window(kind, options)
        day = session.entry_at.date()
        window_start = datetime.combine(day, parse_time(start_text), session.entry_at.tzinfo)
        window_end = datetime.combine(day, parse_time(end_text), session.entry_at.tzinfo)
        duration = choose_duration(kind, options, rng)
        step = max(1, int(options.get(CONF_RANDOM_STEP_MINUTES, 1)))
        candidates: list[datetime] = []
        candidate = window_start
        while candidate <= window_end:
            end = candidate + timedelta(minutes=duration)
            if (
                session.entry_at < candidate
                and end < session.exit_at
                and not any(candidate < pause.end and pause.start < end for pause in pauses)
            ):
                candidates.append(candidate)
            candidate += timedelta(minutes=step)
        if not candidates:
            raise ScheduleError(f"No cabe una pausa {kind.value} válida en la jornada")
        start = rng.choice(candidates)
        pauses.append(Pause(kind, start, start + timedelta(minutes=duration), True))
    return sorted(pauses, key=lambda pause: pause.start)


def build_payload(session: WorkSession, options: Mapping[str, Any]) -> dict[str, Any]:
    """Build the single complete Bizneo logged-time payload."""
    if session.entry_at is None or session.exit_at is None or session.work_date is None:
        raise ScheduleError("La jornada está incompleta")
    if session.entry_at.date() != session.exit_at.date():
        raise ScheduleError("La entrada y la salida deben pertenecer al mismo día")
    pauses = sorted(session.pauses, key=lambda pause: pause.start)
    cursor = session.entry_at
    hours: list[dict[str, Any]] = []
    for pause in pauses:
        if pause.start <= cursor or pause.end >= session.exit_at:
            raise ScheduleError("Las pausas no caben dentro de la jornada")
        hours.append({"start_at": _api_time(cursor), "end_at": _api_time(pause.start)})
        if options.get(CONF_PAUSES_AS_REST):
            rest_id = int(
                options[CONF_SHORT_REST_ID]
                if pause.kind is PauseType.SHORT
                else options[CONF_LONG_REST_ID]
            )
            if rest_id <= 0:
                raise ScheduleError(f"Falta el ID de descanso para la pausa {pause.kind.value}")
            hours.append(
                {
                    "start_at": _api_time(pause.start),
                    "end_at": _api_time(pause.end),
                    "rest": rest_id,
                }
            )
        cursor = pause.end
    hours.append({"start_at": _api_time(cursor), "end_at": _api_time(session.exit_at)})
    return {"logged_time": {"date": session.work_date, "logged_hours": hours}}


def _api_time(value: datetime) -> str:
    return value.strftime("%H:%M:%S")
