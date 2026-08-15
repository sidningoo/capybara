"""Central configuration, loaded from environment / .env.

All tunables live here so the rest of the codebase never reads os.environ directly.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Alpaca ---
    alpaca_api_key: str = Field(default="", alias="ALPACA_API_KEY")
    alpaca_secret_key: str = Field(default="", alias="ALPACA_SECRET_KEY")
    alpaca_paper: bool = Field(default=True, alias="ALPACA_PAPER")

    # --- Universe ---
    universe: str = Field(default="SPY,QQQ,AAPL,MSFT,NVDA", alias="CAPYBARA_UNIVERSE")

    # --- Autonomy ---
    autonomy_level: int = Field(default=1, alias="CAPYBARA_AUTONOMY_LEVEL")
    loop_interval_seconds: int = Field(default=300, alias="CAPYBARA_LOOP_INTERVAL_SECONDS")

    # --- Risk guardrails ---
    max_daily_loss_pct: float = Field(default=3.0, alias="CAPYBARA_MAX_DAILY_LOSS_PCT")
    max_drawdown_pct: float = Field(default=15.0, alias="CAPYBARA_MAX_DRAWDOWN_PCT")
    max_position_pct: float = Field(default=20.0, alias="CAPYBARA_MAX_POSITION_PCT")
    max_concurrent_positions: int = Field(default=5, alias="CAPYBARA_MAX_CONCURRENT_POSITIONS")
    max_gross_exposure_pct: float = Field(default=100.0, alias="CAPYBARA_MAX_GROSS_EXPOSURE_PCT")
    max_orders_per_min: int = Field(default=10, alias="CAPYBARA_MAX_ORDERS_PER_MIN")
    approval_order_notional: float = Field(default=5000.0, alias="CAPYBARA_APPROVAL_ORDER_NOTIONAL")

    # --- Risk hardening (Phase 2) ---
    enable_vol_targeting: bool = Field(default=True, alias="CAPYBARA_ENABLE_VOL_TARGETING")
    target_vol: float = Field(default=0.15, alias="CAPYBARA_TARGET_VOL")  # annualized
    max_sector_pct: float = Field(default=40.0, alias="CAPYBARA_MAX_SECTOR_PCT")
    enable_correlation_control: bool = Field(default=True, alias="CAPYBARA_ENABLE_CORRELATION_CONTROL")
    enable_bracket_orders: bool = Field(default=True, alias="CAPYBARA_ENABLE_BRACKET_ORDERS")

    # --- Selector (Phase 2) ---
    selector_type: str = Field(default="rules", alias="CAPYBARA_SELECTOR")  # "rules" | "bandit"
    bandit_model_path: str = Field(default="./bandit_model.npz", alias="CAPYBARA_BANDIT_MODEL_PATH")
    scores_path: str = Field(default="", alias="CAPYBARA_SCORES_PATH")  # optional Stage-1 score table

    # --- Persistence ---
    db_path: str = Field(default="./capybara.db", alias="CAPYBARA_DB_PATH")

    # --- API ---
    api_host: str = Field(default="0.0.0.0", alias="CAPYBARA_API_HOST")
    api_port: int = Field(default=8000, alias="CAPYBARA_API_PORT")
    cors_origins: str = Field(default="http://localhost:3000", alias="CAPYBARA_CORS_ORIGINS")
    api_token: str = Field(default="change_me", alias="CAPYBARA_API_TOKEN")

    @field_validator("autonomy_level")
    @classmethod
    def _check_level(cls, v: int) -> int:
        if v not in (0, 1, 2):
            raise ValueError("autonomy_level must be 0, 1, or 2")
        return v

    @property
    def universe_list(self) -> list[str]:
        return [s.strip().upper() for s in self.universe.split(",") if s.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        return [s.strip() for s in self.cors_origins.split(",") if s.strip()]

    @property
    def has_alpaca_creds(self) -> bool:
        return bool(self.alpaca_api_key and self.alpaca_secret_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
