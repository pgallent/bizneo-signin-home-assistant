"""Constants for Bizneo Signin."""

from __future__ import annotations

from enum import StrEnum

DOMAIN = "bizneo_signin"
PLATFORMS = ["binary_sensor", "sensor"]
STORAGE_VERSION = 1

CONF_BIZNEO_DOMAIN = "bizneo_domain"
CONF_USER_ID = "user_id"
CONF_TOKEN = "token"
CONF_TRACKED_ENTITY = "tracked_entity"
CONF_WORK_ZONE = "work_zone"
CONF_ENTRY_WINDOW_START = "entry_window_start"
CONF_ENTRY_WINDOW_END = "entry_window_end"
CONF_EXIT_WINDOW_START = "exit_window_start"
CONF_EXIT_WINDOW_END = "exit_window_end"
CONF_FRIDAY_EXIT_WINDOW_START = "friday_exit_window_start"
CONF_FRIDAY_EXIT_WINDOW_END = "friday_exit_window_end"
CONF_ENTRY_DWELL_MINUTES = "entry_dwell_minutes"
CONF_EXIT_DWELL_MINUTES = "exit_dwell_minutes"
CONF_SHORT_PAUSE_WINDOW_START = "short_pause_window_start"
CONF_SHORT_PAUSE_WINDOW_END = "short_pause_window_end"
CONF_LONG_PAUSE_WINDOW_START = "long_pause_window_start"
CONF_LONG_PAUSE_WINDOW_END = "long_pause_window_end"
CONF_SHORT_PAUSE_MIN_MINUTES = "short_pause_min_minutes"
CONF_SHORT_PAUSE_MAX_MINUTES = "short_pause_max_minutes"
CONF_LONG_PAUSE_MIN_MINUTES = "long_pause_min_minutes"
CONF_LONG_PAUSE_MAX_MINUTES = "long_pause_max_minutes"
CONF_RANDOMIZE_PAUSE_DURATIONS = "randomize_pause_durations"
CONF_RANDOM_STEP_MINUTES = "random_step_minutes"
CONF_COMMUNITY = "community"
CONF_NON_WORKING_DATES = "non_working_dates"
CONF_PAUSES_AS_REST = "pauses_as_rest"
CONF_SHORT_REST_ID = "short_rest_id"
CONF_LONG_REST_ID = "long_rest_id"

# National holidays only, no autonomous community.
COMMUNITY_NONE = "none"
# holidays.Spain subdivision codes, ordered by their Spanish name for the UI dropdown.
COMMUNITY_CODES = (
    "AN",  # Andalucía
    "AR",  # Aragón
    "AS",  # Asturias
    "CN",  # Canarias
    "CB",  # Cantabria
    "CM",  # Castilla-La Mancha
    "CL",  # Castilla y León
    "CT",  # Cataluña
    "CE",  # Ceuta
    "VC",  # Comunidad Valenciana
    "EX",  # Extremadura
    "GA",  # Galicia
    "IB",  # Islas Baleares
    "RI",  # La Rioja
    "MD",  # Madrid
    "ML",  # Melilla
    "MC",  # Murcia
    "NC",  # Navarra
    "PV",  # País Vasco
)

DEFAULT_OPTIONS = {
    CONF_ENTRY_WINDOW_START: "07:00",
    CONF_ENTRY_WINDOW_END: "10:00",
    CONF_EXIT_WINDOW_START: "15:30",
    CONF_EXIT_WINDOW_END: "19:00",
    CONF_FRIDAY_EXIT_WINDOW_START: "13:30",
    CONF_FRIDAY_EXIT_WINDOW_END: "17:00",
    CONF_ENTRY_DWELL_MINUTES: 5,
    CONF_EXIT_DWELL_MINUTES: 5,
    CONF_SHORT_PAUSE_WINDOW_START: "10:00",
    CONF_SHORT_PAUSE_WINDOW_END: "11:45",
    CONF_LONG_PAUSE_WINDOW_START: "13:30",
    CONF_LONG_PAUSE_WINDOW_END: "14:30",
    CONF_SHORT_PAUSE_MIN_MINUTES: 15,
    CONF_SHORT_PAUSE_MAX_MINUTES: 15,
    CONF_LONG_PAUSE_MIN_MINUTES: 30,
    CONF_LONG_PAUSE_MAX_MINUTES: 30,
    CONF_RANDOMIZE_PAUSE_DURATIONS: False,
    CONF_RANDOM_STEP_MINUTES: 1,
    CONF_COMMUNITY: COMMUNITY_NONE,
    CONF_NON_WORKING_DATES: "",
    CONF_PAUSES_AS_REST: False,
    CONF_SHORT_REST_ID: 0,
    CONF_LONG_REST_ID: 0,
}

EVENT_STARTED = f"{DOMAIN}_started"
EVENT_PAUSE = f"{DOMAIN}_pause"
EVENT_EXIT = f"{DOMAIN}_exit"
EVENT_SUBMITTED = f"{DOMAIN}_submitted"
EVENT_ERROR = f"{DOMAIN}_error"
SIGNAL_UPDATE = f"{DOMAIN}_update"

SERVICE_REGISTER_PAUSE = "registrar_pausa"
SERVICE_MANUAL_START = "iniciar_jornada_manual"
SERVICE_MANUAL_FINISH = "finalizar_jornada_manual"
SERVICE_DISCARD = "descartar_jornada"
SERVICE_RETRY = "reintentar_envio"
SERVICE_RESOLVE_UNCERTAIN = "resolver_envio_dudoso"


class SigninState(StrEnum):
    """Runtime state machine states."""

    IDLE = "idle"
    ENTRY_PENDING = "entry_pending"
    WORKING = "working"
    EXIT_PENDING = "exit_pending"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class PauseType(StrEnum):
    """Supported pause types."""

    SHORT = "corta"
    LONG = "larga"


class SubmitResult(StrEnum):
    """Result returned by the Bizneo API client."""

    OK = "ok"
    ERROR = "error"
    UNCERTAIN = "uncertain"
