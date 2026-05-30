from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock

from .crypto import DerivedKeys, HandshakeTranscript
from .replay import SessionReplayState


@dataclass
class SecureSession:
    """Runtime state for one encrypted session.

    The lock serializes request/response exchanges so strict sequence numbers cannot
    be allocated or received out of order within the same session.
    """

    transcript: HandshakeTranscript
    keys: DerivedKeys
    replay: SessionReplayState = field(default_factory=SessionReplayState)
    lock: RLock = field(default_factory=RLock)


class SecureSessionStore:
    """Small process-local session store for the current single-instance deployment."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: dict[str, SecureSession] = {}

    def put(self, session: SecureSession) -> None:
        with self._lock:
            self._sessions[session.transcript.session_id] = session

    def get(self, session_id: str) -> SecureSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def contains(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._sessions

    def first(self) -> SecureSession | None:
        with self._lock:
            return next(iter(self._sessions.values()), None)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()
