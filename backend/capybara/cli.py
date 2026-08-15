"""Capybara command-line entry point.

    capybara backtest [--synthetic | --symbols SPY,QQQ] [--days 600]
    capybara run                # start the live paper-trading loop + API
    capybara api                # start only the control-plane API

Live modes require Alpaca paper credentials in the environment / .env.
"""
from __future__ import annotations

import argparse
import sys

from capybara.config import get_settings
from capybara.logging_setup import get_logger, setup_logging

log = get_logger("cli")


def cmd_backtest(args: argparse.Namespace) -> int:
    from capybara.backtest.runner import Backtester
    from capybara.backtest.synthetic import make_universe

    s = get_settings()
    symbols = [x.strip().upper() for x in args.symbols.split(",")] if args.symbols else s.universe_list

    if args.synthetic or not s.has_alpaca_creds:
        log.info("Backtest on SYNTHETIC data (%d symbols, %d days).", len(symbols), args.days)
        bars = make_universe(symbols, n_days=args.days)
    else:
        log.info("Backtest on ALPACA historical data (%d symbols).", len(symbols))
        from datetime import datetime, timedelta, timezone

        from capybara.broker.alpaca import AlpacaBroker
        broker = AlpacaBroker(s.alpaca_api_key, s.alpaca_secret_key, paper=s.alpaca_paper)
        end = datetime.now(timezone.utc) - timedelta(minutes=20)
        start = end - timedelta(days=int(args.days * 1.6))  # calendar buffer for trading days
        bars = broker.get_bars(symbols, timeframe="1Day", start=start, end=end)

    bt = Backtester(bars)
    result = bt.run()
    print("\n=== Backtest result ===")
    print(result.summary())
    print("per-strategy fills:", result.per_strategy_fills)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from capybara.api.app import serve
    serve(start_engine=True)
    return 0


def cmd_api(args: argparse.Namespace) -> int:
    from capybara.api.app import serve
    serve(start_engine=False)
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = argparse.ArgumentParser(prog="capybara", description="Autonomous Alpaca paper-trading bot.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_bt = sub.add_parser("backtest", help="Run a backtest.")
    p_bt.add_argument("--synthetic", action="store_true", help="Use synthetic data (no network).")
    p_bt.add_argument("--symbols", default="", help="Comma-separated symbols (defaults to universe).")
    p_bt.add_argument("--days", type=int, default=600, help="Number of days to simulate.")
    p_bt.set_defaults(func=cmd_backtest)

    p_run = sub.add_parser("run", help="Start live paper-trading loop + control API.")
    p_run.set_defaults(func=cmd_run)

    p_api = sub.add_parser("api", help="Start only the control-plane API.")
    p_api.set_defaults(func=cmd_api)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
