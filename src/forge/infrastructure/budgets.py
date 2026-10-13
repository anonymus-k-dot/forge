"""Per-run budgets (spec §19, ADR-008, ADR-018).

Dimensions (stored in ``runs.budget_limits``):
    max_model_calls          required; every provider *attempt* (retries and failed attempts
                             included) consumes 1 before it is sent; nothing is refunded
    max_estimated_tokens     optional; each attempt reserves an estimate (input chars / 4 +
                             max_output_tokens), reconciled after the call to provider-reported
                             usage when both counts are reported, else the estimate is kept
    max_cases, max_samples_per_case, max_candidates
                             optional structural limits checked before a run starts
    confirm_above_model_calls
                             optional; a plan whose worst-case call count exceeds it needs
                             explicit confirmation

Cache hits consume nothing; they are counted separately (``cache_hits``). A run whose
budget is exhausted is marked ``budget_exceeded``; its recorded results are kept.
"""

from __future__ import annotations

import logging
import math
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError
from sqlalchemy import text

from forge.db.session import Database
from forge.errors import ConfigurationError, ForgeError
from forge.providers.base import GenerationRequest, Usage

logger = logging.getLogger(__name__)

ACTIVE_RUN_STATUSES = ("pending", "running")
MAX_CALL_LIMIT = 1_000_000
MAX_TOKEN_LIMIT = 10_000_000_000
CHARS_PER_TOKEN = 4  # documented heuristic; counts derived from it are "estimated"


# ── errors (stable codes for future API mapping) ──────────────────────────


class InvalidBudgetError(ConfigurationError):
    code = "invalid_budget"


class BudgetExceededError(ForgeError):
    """No model call was made: the run's budget does not allow it."""

    code = "budget_exceeded"

    def __init__(self, dimension: str) -> None:
        super().__init__(f"The run's budget is exhausted ({dimension}).")
        self.dimension = dimension


class BudgetConfirmationRequiredError(ForgeError):
    code = "budget_confirmation_required"

    def __init__(self, estimated_calls: int, threshold: int) -> None:
        super().__init__(
            f"The run may make up to {estimated_calls} model calls, above the confirmation "
            f"threshold of {threshold}; explicit confirmation is required."
        )
        self.estimated_calls = estimated_calls
        self.threshold = threshold


class RunNotActiveError(ForgeError):
    code = "run_not_active"

    def __init__(self, status: str | None) -> None:
        super().__init__(f"The run is not active (status: {status or 'missing'}).")
        self.status = status


# ── limits and planning ────────────────────────────────────────────────────


class BudgetLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_model_calls: StrictInt = Field(ge=1, le=MAX_CALL_LIMIT)
    max_estimated_tokens: StrictInt | None = Field(default=None, ge=1, le=MAX_TOKEN_LIMIT)
    max_cases: StrictInt | None = Field(default=None, ge=1, le=MAX_CALL_LIMIT)
    max_samples_per_case: StrictInt | None = Field(default=None, ge=1, le=1000)
    max_candidates: StrictInt | None = Field(default=None, ge=1, le=1000)
    confirm_above_model_calls: StrictInt | None = Field(default=None, ge=1, le=MAX_CALL_LIMIT)

    @classmethod
    def parse(cls, data: Any) -> BudgetLimits:
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
                for err in exc.errors()
            )
            raise InvalidBudgetError(f"Invalid budget: {problems}") from None

    def to_json(self) -> dict[str, int]:
        return self.model_dump(exclude_none=True)


@dataclass(frozen=True)
class RunPlan:
    cases: int
    systems: int
    samples_per_case: int = 1
    calls_per_execution: int = 1
    candidates: int | None = None


@dataclass(frozen=True)
class BudgetEstimate:
    min_model_calls: int  # every call succeeds first time
    max_model_calls: int  # every call uses all retry attempts


def check_plan(
    limits: BudgetLimits, plan: RunPlan, *, max_attempts: int, confirmed: bool = False
) -> BudgetEstimate:
    """Validate a run plan against its limits before anything executes."""
    for name, value in (
        ("cases", plan.cases),
        ("systems", plan.systems),
        ("samples_per_case", plan.samples_per_case),
        ("calls_per_execution", plan.calls_per_execution),
        ("max_attempts", max_attempts),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise InvalidBudgetError(f"Invalid run plan: {name} must be a positive integer.")
    for dimension, planned, limit in (
        ("cases", plan.cases, limits.max_cases),
        ("samples_per_case", plan.samples_per_case, limits.max_samples_per_case),
        ("candidates", plan.candidates, limits.max_candidates),
    ):
        if limit is not None and planned is not None and planned > limit:
            raise BudgetExceededError(dimension)
    minimum = plan.cases * plan.systems * plan.samples_per_case * plan.calls_per_execution
    estimate = BudgetEstimate(min_model_calls=minimum, max_model_calls=minimum * max_attempts)
    if estimate.min_model_calls > limits.max_model_calls:
        raise BudgetExceededError("model_calls")
    threshold = limits.confirm_above_model_calls
    if threshold is not None and estimate.max_model_calls > threshold and not confirmed:
        raise BudgetConfirmationRequiredError(estimate.max_model_calls, threshold)
    return estimate


def estimate_reservation_tokens(request: GenerationRequest) -> int | None:
    """Conservative token estimate for one attempt, or ``None`` if output is unbounded."""
    if request.params.max_output_tokens is None:
        return None
    chars = len(request.system or "") + sum(len(m.content) for m in request.messages)
    return math.ceil(chars / CHARS_PER_TOKEN) + request.params.max_output_tokens


# ── guards ─────────────────────────────────────────────────────────────────


@dataclass
class Reservation:
    tokens: int
    settled: bool = False


@dataclass(frozen=True)
class Settlement:
    tokens_charged: int
    source: str  # "provider" | "estimated"


def settle_tokens(reservation: Reservation, usage: Usage | None) -> Settlement:
    if usage is not None and usage.input_tokens is not None and usage.output_tokens is not None:
        return Settlement(usage.input_tokens + usage.output_tokens, "provider")
    return Settlement(reservation.tokens, "estimated")


class BudgetGuard(Protocol):
    def reserve(self, request: GenerationRequest) -> Reservation:
        """Atomically consume one call (and reserve tokens) or raise; never partially."""
        ...

    def settle(self, reservation: Reservation, usage: Usage | None) -> Settlement:
        """Release the token reservation and charge actual-or-estimated tokens."""
        ...

    def record_cache_hit(self) -> None: ...


def _required_tokens(limits: BudgetLimits, request: GenerationRequest) -> int:
    estimate = estimate_reservation_tokens(request)
    if limits.max_estimated_tokens is None:
        return estimate or 0
    if estimate is None:
        raise InvalidBudgetError(
            "A token budget requires max_output_tokens to be set on every request."
        )
    return estimate


class MemoryRunBudget:
    """In-process budget for tests and database-less runs (same rules as PostgreSQL)."""

    def __init__(self, limits: BudgetLimits) -> None:
        self.limits = limits
        self.model_calls_used = 0
        self.tokens_used = 0
        self.tokens_reserved = 0
        self.cache_hits = 0
        self.exceeded: str | None = None
        self._lock = threading.Lock()

    def reserve(self, request: GenerationRequest) -> Reservation:
        tokens = _required_tokens(self.limits, request)
        with self._lock:
            if self.exceeded is not None:
                raise BudgetExceededError(self.exceeded)
            if self.model_calls_used + 1 > self.limits.max_model_calls:
                self.exceeded = "model_calls"
                raise BudgetExceededError("model_calls")
            token_limit = self.limits.max_estimated_tokens
            if (
                token_limit is not None
                and self.tokens_used + self.tokens_reserved + tokens > token_limit
            ):
                self.exceeded = "tokens"
                raise BudgetExceededError("tokens")
            self.model_calls_used += 1
            self.tokens_reserved += tokens
        return Reservation(tokens)

    def settle(self, reservation: Reservation, usage: Usage | None) -> Settlement:
        if reservation.settled:
            raise RuntimeError("reservation already settled")
        settlement = settle_tokens(reservation, usage)
        with self._lock:
            self.tokens_reserved -= reservation.tokens
            self.tokens_used += settlement.tokens_charged
        reservation.settled = True
        return settlement

    def record_cache_hit(self) -> None:
        with self._lock:
            self.cache_hits += 1


_RESERVE_SQL = text(
    """
    UPDATE runs
       SET model_calls_used = model_calls_used + 1,
           tokens_reserved = tokens_reserved + :tokens
     WHERE id = :run_id
       AND status IN ('pending', 'running')
       AND model_calls_used + 1 <= (budget_limits->>'max_model_calls')::bigint
       AND (budget_limits->>'max_estimated_tokens' IS NULL
            OR tokens_used + tokens_reserved + :tokens
               <= (budget_limits->>'max_estimated_tokens')::bigint)
    RETURNING model_calls_used
    """
)


class PostgresRunBudget:
    """Budget for one ``runs`` row. Reservations are single conditional UPDATEs, so concurrent
    workers cannot overspend; any database failure raises (fail closed: no call is made)."""

    def __init__(self, database: Database, run_id: uuid.UUID) -> None:
        self._database = database
        self.run_id = run_id
        self._limits: BudgetLimits | None = None

    def limits(self) -> BudgetLimits:
        if self._limits is None:
            with self._database.session() as session:
                raw = session.execute(
                    text("SELECT budget_limits FROM runs WHERE id = :id"), {"id": self.run_id}
                ).scalar_one_or_none()
            if raw is None:
                raise RunNotActiveError(None)
            self._limits = BudgetLimits.parse(raw)
        return self._limits

    def reserve(self, request: GenerationRequest) -> Reservation:
        tokens = _required_tokens(self.limits(), request)
        with self._database.session() as session:
            reserved = session.execute(
                _RESERVE_SQL, {"run_id": self.run_id, "tokens": tokens}
            ).scalar_one_or_none()
            if reserved is not None:
                return Reservation(tokens)
            row = session.execute(
                text(
                    "SELECT status, model_calls_used, tokens_used, tokens_reserved, budget_limits "
                    "FROM runs WHERE id = :id FOR UPDATE"
                ),
                {"id": self.run_id},
            ).one_or_none()
            if row is None or row.status not in ACTIVE_RUN_STATUSES:
                raise RunNotActiveError(None if row is None else row.status)
            limits = BudgetLimits.parse(row.budget_limits)
            token_limit = limits.max_estimated_tokens
            if row.model_calls_used + 1 > limits.max_model_calls:
                dimension = "model_calls"
            elif (
                token_limit is not None
                and row.tokens_used + row.tokens_reserved + tokens > token_limit
            ):
                dimension = "tokens"
            else:
                # A concurrent settlement released tokens between the UPDATE and this lock:
                # the reservation fits now, so take it under the row lock.
                session.execute(
                    text(
                        "UPDATE runs SET model_calls_used = model_calls_used + 1, "
                        "tokens_reserved = tokens_reserved + :tokens WHERE id = :id"
                    ),
                    {"id": self.run_id, "tokens": tokens},
                )
                return Reservation(tokens)
            session.execute(
                text("UPDATE runs SET status = 'budget_exceeded' WHERE id = :id"),
                {"id": self.run_id},
            )
        logger.warning(
            "budget.exceeded", extra={"forge": {"run_id": str(self.run_id), "dimension": dimension}}
        )
        raise BudgetExceededError(dimension)

    def settle(self, reservation: Reservation, usage: Usage | None) -> Settlement:
        if reservation.settled:
            raise RuntimeError("reservation already settled")
        settlement = settle_tokens(reservation, usage)
        with self._database.session() as session:
            session.execute(
                text(
                    "UPDATE runs SET tokens_reserved = tokens_reserved - :reserved, "
                    "tokens_used = tokens_used + :charged WHERE id = :id"
                ),
                {
                    "id": self.run_id,
                    "reserved": reservation.tokens,
                    "charged": settlement.tokens_charged,
                },
            )
        reservation.settled = True
        return settlement

    def record_cache_hit(self) -> None:
        with self._database.session() as session:
            session.execute(
                text("UPDATE runs SET cache_hits = cache_hits + 1 WHERE id = :id"),
                {"id": self.run_id},
            )
