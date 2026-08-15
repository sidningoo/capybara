"""Portfolio-level exposure controls: sectors, volatility targeting, correlation.

These make the autonomous book behave less like a naive equal-weighter and more
like a risk-managed portfolio — important when the user is hands-off and not
watching every position.
"""
from __future__ import annotations

import numpy as np

# Minimal sector map for the default universe + common names/ETFs. Unknown symbols
# fall into "other". Extend as the universe grows (or wire a real classifier later).
SECTOR_MAP: dict[str, str] = {
    # Broad-market ETFs get their own bucket so index exposure is capped sensibly.
    "SPY": "index_etf", "QQQ": "index_etf", "IWM": "index_etf", "DIA": "index_etf",
    "VTI": "index_etf", "VOO": "index_etf",
    # Sector ETFs
    "XLK": "technology", "XLF": "financials", "XLE": "energy", "XLV": "healthcare",
    # Tech / comms
    "AAPL": "technology", "MSFT": "technology", "NVDA": "technology", "AVGO": "technology",
    "AMD": "technology", "CRM": "technology", "ADBE": "technology", "ORCL": "technology",
    "GOOGL": "communication", "GOOG": "communication", "META": "communication",
    "NFLX": "communication",
    # Consumer
    "AMZN": "consumer_disc", "TSLA": "consumer_disc", "HD": "consumer_disc",
    "COST": "consumer_staples", "WMT": "consumer_staples",
    # Financials / healthcare / energy
    "JPM": "financials", "BAC": "financials", "V": "financials", "MA": "financials",
    "UNH": "healthcare", "JNJ": "healthcare", "LLY": "healthcare",
    "XOM": "energy", "CVX": "energy",
}


def sector_of(symbol: str) -> str:
    return SECTOR_MAP.get(symbol.upper(), "other")


def vol_target_scale(
    realized_vol: float | None,
    target_vol: float,
    lo: float = 0.3,
    hi: float = 1.5,
) -> float:
    """Scale a position by target/realized volatility (inverse-vol sizing).

    High-vol names get smaller allocations, low-vol names larger — bounded so we
    never lever up aggressively. Returns 1.0 if realized vol is unknown/zero.
    """
    if not realized_vol or realized_vol <= 0:
        return 1.0
    return float(np.clip(target_vol / realized_vol, lo, hi))


def enforce_sector_caps(
    weights: dict[str, float],
    max_sector_pct: float,
) -> tuple[dict[str, float], list[str]]:
    """Scale down symbols so no sector exceeds `max_sector_pct` of equity.

    Returns (adjusted_weights, notes).
    """
    cap = max_sector_pct / 100.0
    notes: list[str] = []
    # Group current target weights by sector.
    by_sector: dict[str, float] = {}
    for sym, w in weights.items():
        if w > 0:
            by_sector[sector_of(sym)] = by_sector.get(sector_of(sym), 0.0) + w
    adjusted = dict(weights)
    for sector, total in by_sector.items():
        if total > cap and total > 0:
            scale = cap / total
            for sym in weights:
                if weights[sym] > 0 and sector_of(sym) == sector:
                    adjusted[sym] = weights[sym] * scale
            notes.append(f"scaled sector '{sector}' by {scale:.2f} (cap {max_sector_pct}%)")
    return adjusted, notes


def correlation_penalty(
    returns: dict[str, np.ndarray],
    symbols: list[str],
    max_penalty: float = 0.4,
    corr_threshold: float = 0.7,
) -> dict[str, float]:
    """Return a per-symbol multiplier (<=1) that trims names highly correlated with
    the rest of the candidate set, so we don't unknowingly concentrate one bet.
    """
    mult = {s: 1.0 for s in symbols}
    usable = [s for s in symbols if s in returns and len(returns[s]) > 5]
    if len(usable) < 2:
        return mult
    # Align lengths.
    min_len = min(len(returns[s]) for s in usable)
    mat = np.vstack([returns[s][-min_len:] for s in usable])
    with np.errstate(invalid="ignore"):
        corr = np.corrcoef(mat)
    for i, s in enumerate(usable):
        others = [corr[i, j] for j in range(len(usable)) if j != i]
        avg_corr = float(np.nanmean(np.abs(others))) if others else 0.0
        if avg_corr > corr_threshold:
            over = (avg_corr - corr_threshold) / (1.0 - corr_threshold)
            mult[s] = float(1.0 - min(max_penalty, max_penalty * over))
    return mult
