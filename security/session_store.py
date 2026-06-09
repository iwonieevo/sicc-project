from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
import time

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
        self._created_at: dict[str, float] = {}

    def put(self, session: SecureSession) -> None:
        with self._lock:
            session_id = session.transcript.session_id
            self._sessions[session_id] = session
            self._created_at[session_id] = time.monotonic()

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
            self._created_at.clear()

    def prune_older_than(self, ttl_seconds: int) -> None:
        with self._lock:
            if ttl_seconds < 1:
                self.clear()
                return
            cutoff = time.monotonic() - ttl_seconds
            stale = [
                session_id
                for session_id, created_at in self._created_at.items()
                if created_at < cutoff
            ]
            for session_id in stale:
                self._sessions.pop(session_id, None)
                self._created_at.pop(session_id, None)
