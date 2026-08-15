"""Pydantic schemas for the control-plane API request bodies."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ManualOrderReq(BaseModel):
    symbol: str
    side: str = Field(description="'buy' or 'sell'")
    qty: float = Field(gt=0)
    reason: str = "manual order via dashboard"


class AutonomyReq(BaseModel):
    level: int = Field(ge=0, le=2)


class PinReq(BaseModel):
    strategy: str | None = Field(default=None, description="strategy name, 'cash', or null to unpin")


class BlockReq(BaseModel):
    strategy: str
    blocked: bool = True


class KillReq(BaseModel):
    flatten: bool = True


class ApprovalReq(BaseModel):
    client_order_id: str


class RiskProfileReq(BaseModel):
    profile: str = Field(description="conservative | balanced | aggressive")


class WatchlistReq(BaseModel):
    symbols: list[str] = Field(description="full replacement watchlist of symbols")
