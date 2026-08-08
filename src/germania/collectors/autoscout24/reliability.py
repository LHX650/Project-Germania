"""Process-local AutoScout24 source reliability controls."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock

from germania.collectors.exceptions import (
    CollectorAccessDeniedError,
    CollectorError,
    RequestBudgetExceeded,
)

_MAX_RETAINED_RUNS = 64
_REGISTRY_LOCK = Lock()
_RUN_STATES: OrderedDict[tuple[str, str], SourceRunState] = OrderedDict()


@dataclass
class SourceRunState:
    """Shared source health and request accounting for one collection run."""

    source_id: str
    run_id: str
    request_budget: int
    _request_count: int = 0
    _preflight_status: str = "not_started"
    _circuit_open: bool = False
    _access_denied: bool = False
    _error_message: str | None = None
    _lock: Lock = field(default_factory=Lock, repr=False)

    @property
    def request_count(self) -> int:
        """Return the number of requests reserved across all cohorts."""

        with self._lock:
            return self._request_count

    @property
    def remaining_request_budget(self) -> int:
        """Return the unreserved source-level request budget."""

        with self._lock:
            return max(self.request_budget - self._request_count, 0)

    @property
    def preflight_required(self) -> bool:
        """Return whether this run still needs its single source preflight."""

        with self._lock:
            return self._preflight_status == "not_started"

    @property
    def circuit_open(self) -> bool:
        """Return whether further requests are blocked for this source run."""

        with self._lock:
            return self._circuit_open

    @property
    def error_message(self) -> str | None:
        """Return the reason the source circuit was opened, if any."""

        with self._lock:
            return self._error_message

    def reserve_request(self) -> None:
        """Reserve one source request or fail before network activity."""

        with self._lock:
            self._raise_if_open_locked()
            if self._request_count >= self.request_budget:
                raise RequestBudgetExceeded(
                    "Source-level request budget exceeded for "
                    f"source_id={self.source_id} run_id={self.run_id} "
                    f"budget={self.request_budget}"
                )
            self._request_count += 1

    def release_request(self) -> None:
        """Release a reservation when local validation rejects the request."""

        with self._lock:
            if self._request_count > 0:
                self._request_count -= 1

    def begin_preflight(self) -> bool:
        """Claim the single preflight request for this source run."""

        with self._lock:
            self._raise_if_open_locked()
            if self._preflight_status in {"running", "completed"}:
                return False
            self._preflight_status = "running"
            return True

    def complete_preflight(self) -> None:
        """Mark the shared source preflight successful."""

        with self._lock:
            if not self._circuit_open:
                self._preflight_status = "completed"

    def open_circuit(self, message: str, *, access_denied: bool) -> None:
        """Prevent further requests for the source in this run."""

        normalized = " ".join(message.split()) or "Source access is unavailable"
        with self._lock:
            self._circuit_open = True
            self._access_denied = self._access_denied or access_denied
            self._error_message = self._error_message or normalized
            self._preflight_status = "failed"

    def raise_if_open(self) -> None:
        """Raise the appropriate collector error when the circuit is open."""

        with self._lock:
            self._raise_if_open_locked()

    def _raise_if_open_locked(self) -> None:
        if not self._circuit_open:
            return
        message = self._error_message or "Source circuit is open"
        if self._access_denied:
            raise CollectorAccessDeniedError(message)
        raise CollectorError(message)


def get_source_run_state(
    source_id: str,
    run_id: str,
    *,
    request_budget: int,
) -> SourceRunState:
    """Return a bounded process-local state shared by cohort collectors."""

    if request_budget <= 0:
        raise ValueError("request_budget must be positive")
    key = (source_id, run_id)
    with _REGISTRY_LOCK:
        state = _RUN_STATES.get(key)
        if state is not None:
            if state.request_budget != request_budget:
                raise ValueError(
                    "Source-level request budget changed within a run: "
                    f"source_id={source_id} run_id={run_id}"
                )
            _RUN_STATES.move_to_end(key)
            return state

        state = SourceRunState(
            source_id=source_id,
            run_id=run_id,
            request_budget=request_budget,
        )
        _RUN_STATES[key] = state
        while len(_RUN_STATES) > _MAX_RETAINED_RUNS:
            _RUN_STATES.popitem(last=False)
        return state


def clear_source_run_states() -> None:
    """Clear process-local source states for isolated tests."""

    with _REGISTRY_LOCK:
        _RUN_STATES.clear()
