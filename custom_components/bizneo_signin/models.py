"""Serializable data models for Bizneo Signin."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .const import PauseType, SigninState


@dataclass(slots=True)
class Pause:
    """A workday pause."""

    kind: PauseType
    start: datetime
    end: datetime
    generated: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize the pause."""
        return {
            "kind": self.kind.value,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "generated": self.generated,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Pause:
        """Deserialize a pause."""
        return cls(
            kind=PauseType(value["kind"]),
            start=datetime.fromisoformat(value["start"]),
            end=datetime.fromisoformat(value["end"]),
            generated=bool(value.get("generated", False)),
        )


@dataclass(slots=True)
class WorkSession:
    """Persisted session and pending crossings."""

    state: SigninState = SigninState.IDLE
    work_date: str | None = None
    entry_at: datetime | None = None
    entry_pending_at: datetime | None = None
    exit_at: datetime | None = None
    exit_pending_at: datetime | None = None
    pauses: list[Pause] = field(default_factory=list)
    payload: dict[str, Any] | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the session."""
        return {
            "state": self.state.value,
            "work_date": self.work_date,
            "entry_at": self.entry_at.isoformat() if self.entry_at else None,
            "entry_pending_at": (
                self.entry_pending_at.isoformat() if self.entry_pending_at else None
            ),
            "exit_at": self.exit_at.isoformat() if self.exit_at else None,
            "exit_pending_at": (self.exit_pending_at.isoformat() if self.exit_pending_at else None),
            "pauses": [pause.to_dict() for pause in self.pauses],
            "payload": self.payload,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> WorkSession:
        """Deserialize a session, returning idle for empty storage."""
        if not value:
            return cls()
        return cls(
            state=SigninState(value.get("state", SigninState.IDLE)),
            work_date=value.get("work_date"),
            entry_at=_parse_datetime(value.get("entry_at")),
            entry_pending_at=_parse_datetime(value.get("entry_pending_at")),
            exit_at=_parse_datetime(value.get("exit_at")),
            exit_pending_at=_parse_datetime(value.get("exit_pending_at")),
            pauses=[Pause.from_dict(item) for item in value.get("pauses", [])],
            payload=value.get("payload"),
            last_error=value.get("last_error"),
        )


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
