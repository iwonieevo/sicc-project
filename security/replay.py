from __future__ import annotations

from dataclasses import dataclass, field

from .crypto import Direction
from .errors import ReplayError


@dataclass
class DirectionState:
    next_send_seq: int = 0
    next_recv_seq: int = 0

    def allocate_send_seq(self) -> int:
        """Return the next sequence number for an outgoing message and advance it."""

        seq = self.next_send_seq
        self.next_send_seq += 1
        return seq

    def accept_recv_seq(self, seq: int) -> None:
        """Accept only the exact next inbound sequence number for this direction."""

        self.check_recv_seq(seq)
        self.next_recv_seq += 1

    def check_recv_seq(self, seq: int) -> None:
        """Validate the next inbound sequence number without committing it."""

        if seq != self.next_recv_seq:
            raise ReplayError(f"expected seq {self.next_recv_seq}, got {seq}")


@dataclass
class SessionReplayState:
    client_to_server: DirectionState = field(default_factory=DirectionState)
    server_to_client: DirectionState = field(default_factory=DirectionState)

    def state_for(self, direction: Direction) -> DirectionState:
        """Return replay state for a typed message direction."""

        if direction == Direction.CLIENT_TO_SERVER:
            return self.client_to_server
        if direction == Direction.SERVER_TO_CLIENT:
            return self.server_to_client
        raise ValueError("unknown direction")
