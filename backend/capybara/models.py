"""Core domain models — the shared vocabulary of the whole system.

These are plain dataclasses/enums (not Pydantic) so they are cheap to create in
hot loops and backtests. Pydantic is reserved for the API boundary (see api/schemas.py).

The key architectural boundary is the *Intent*: strategies emit Intents describing
what they *want* the portfolio to look like. The risk manager turns approved Intents
into Orders. Strategies never create Orders directly and never touch the broker.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────── Market data ───────────────────────────
@dataclass(frozen=True, slots=True)
class Bar:
    """A single OHLCV candle for one symbol."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


# ─────────────────────────── Regime ───────────────────────────
class Regime(str, Enum):
    """Coarse market regimes the selector reasons over.

    Deliberately small and interpretable for Stage 1. The NLP/ML selector in a
    later phase can produce a richer context vector, but these labels remain a
    human-readable projection of it.
    """
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    MEAN_REVERTING = "mean_reverting"
    HIGH_VOLATILITY = "high_volatility"
    QUIET = "quiet"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RegimeReading:
    """Regime classification for one symbol at one point in time, plus the raw
    features that produced it (so decisions are explainable / auditable)."""
    symbol: str
    regime: Regime
    confidence: float  # 0..1
    features: dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=utcnow)


# ─────────────────────────── Strategy output ───────────────────────────
class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class SignalDirection(str, Enum):
    LONG = "long"
    FLAT = "flat"
    # SHORT reserved for a later phase; long-only to start (paper equities).
    SHORT = "short"


@dataclass(frozen=True, slots=True)
class Intent:
    """What a strategy *wants* for one symbol, expressed as a target.

    `target_weight` is the fraction of total equity the strategy wants allocated
    to this symbol (0..1 for long-only). The risk manager decides whether/how much
    of this to honor and converts the delta vs. current holdings into Orders.
    """
    symbol: str
    direction: SignalDirection
    target_weight: float                 # desired fraction of equity (0..1)
    strategy: str                        # name of the strategy that produced it
    confidence: float = 0.5              # 0..1
    reason: str = ""                     # human-readable rationale (shown in UI)
    stop_loss: float | None = None       # optional absolute price
    take_profit: float | None = None     # optional absolute price
    timestamp: datetime = field(default_factory=utcnow)


# ─────────────────────────── Orders / fills / positions ───────────────────────────
class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class TimeInForce(str, Enum):
    DAY = "day"
    GTC = "gtc"


class OrderClass(str, Enum):
    SIMPLE = "simple"
    BRACKET = "bracket"  # entry + attached take-profit + stop-loss


class OrderStatus(str, Enum):
    NEW = "new"                  # created locally, not yet sent
    PENDING_APPROVAL = "pending_approval"  # HILT gate (autonomy L0/L1)
    SUBMITTED = "submitted"      # accepted by broker
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


TERMINAL_STATUSES = {
    OrderStatus.FILLED,
    OrderStatus.CANCELED,
    OrderStatus.REJECTED,
    OrderStatus.EXPIRED,
}


@dataclass(slots=True)
class Order:
    """An order as Capybara understands it. `broker_order_id` links to Alpaca."""
    symbol: str
    side: Side
    qty: float
    order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY
    limit_price: float | None = None
    status: OrderStatus = OrderStatus.NEW
    filled_qty: float = 0.0
    filled_avg_price: float | None = None
    # bracket / protective legs (optional)
    order_class: OrderClass = OrderClass.SIMPLE
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    # provenance
    strategy: str = "manual"
    reason: str = ""
    client_order_id: str = ""       # our idempotency key
    broker_order_id: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def notional(self) -> float | None:
        px = self.limit_price or self.filled_avg_price
        return None if px is None else px * self.qty


@dataclass(frozen=True, slots=True)
class Fill:
    symbol: str
    side: Side
    qty: float
    price: float
    order_id: str
    timestamp: datetime = field(default_factory=utcnow)


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float

    @property
    def market_value(self) -> float:
        return self.qty * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.qty * self.avg_entry_price

    @property
    def unrealized_pl(self) -> float:
        return self.market_value - self.cost_basis

    @property
    def unrealized_pl_pct(self) -> float:
        if self.cost_basis == 0:
            return 0.0
        return self.unrealized_pl / abs(self.cost_basis) * 100.0


@dataclass(frozen=True, slots=True)
class Account:
    equity: float
    cash: float
    buying_power: float
    currency: str = "USD"
    timestamp: datetime = field(default_factory=utcnow)


# ─────────────────────────── Engine state ───────────────────────────
class EngineState(str, Enum):
    """States of the orchestrator's control loop / state machine."""
    IDLE = "idle"            # not started
    RUNNING = "running"      # loop active, market open
    PAUSED = "paused"        # human paused; no new orders, positions kept
    HALTED = "halted"        # guardrail tripped or kill switch; no trading
    MARKET_CLOSED = "market_closed"  # waiting for next session


class AutonomyLevel(int, Enum):
    APPROVAL = 0     # every order queues for approval
    AUTO_LIMITED = 1  # auto within limits; unusual orders queue
    FULL_AUTO = 2    # auto within guardrails
