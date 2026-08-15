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


def _load_bars(args, s):
    """Load historical bars for a command: synthetic (offline) or Alpaca."""
    from capybara.backtest.synthetic import make_universe

    symbols = [x.strip().upper() for x in args.symbols.split(",")] if args.symbols else s.universe_list
    if getattr(args, "synthetic", False) or not s.has_alpaca_creds:
        log.info("Using SYNTHETIC data (%d symbols, %d days).", len(symbols), args.days)
        return make_universe(symbols, n_days=args.days)
    log.info("Using ALPACA historical data (%d symbols).", len(symbols))
    from datetime import datetime, timedelta, timezone

    from capybara.broker.alpaca import AlpacaBroker
    broker = AlpacaBroker(s.alpaca_api_key, s.alpaca_secret_key, paper=s.alpaca_paper)
    end = datetime.now(timezone.utc) - timedelta(minutes=20)
    start = end - timedelta(days=int(args.days * 1.6))
    return broker.get_bars(symbols, timeframe="1Day", start=start, end=end)


def cmd_backtest(args: argparse.Namespace) -> int:
    from capybara.backtest.runner import Backtester

    s = get_settings()
    bars = _load_bars(args, s)

    selector = None
    if getattr(args, "bandit", False):
        from capybara.selector.bandit import LinUCBSelector
        selector = LinUCBSelector.load(args.model or s.bandit_model_path)
        log.info("Backtesting with LinUCB bandit selector.")

    bt = Backtester(bars, selector=selector)
    result = bt.run()
    print("\n=== Backtest result ===")
    print(result.summary())
    print("per-strategy fills:", result.per_strategy_fills)
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    """Train the LinUCB bandit selector offline and save the model."""
    from capybara.backtest.walkforward import BanditTrainer

    s = get_settings()
    bars = _load_bars(args, s)
    trainer = BanditTrainer(horizon=args.horizon, alpha=args.alpha)
    bandit = trainer.train(bars)
    out = args.out or s.bandit_model_path
    bandit.save(out)
    print(f"\n✓ Bandit model trained and saved to {out}")
    print("  Set CAPYBARA_SELECTOR=bandit (or use `backtest --bandit`) to use it.")
    return 0


def cmd_walkforward(args: argparse.Namespace) -> int:
    """Out-of-sample validation via rolling train/test folds."""
    from capybara.backtest.walkforward import WalkForwardValidator

    s = get_settings()
    bars = _load_bars(args, s)
    wf = WalkForwardValidator(bars, n_folds=args.folds, horizon=args.horizon)
    report = wf.run()
    print("\n=== Walk-forward validation ===")
    print(report.summary())
    return 0


def cmd_attribution(args: argparse.Namespace) -> int:
    """Learn the Stage-1 regime->strategy score table from history and save it."""
    from capybara.backtest.attribution import compute_regime_scores, save_scores

    s = get_settings()
    bars = _load_bars(args, s)
    scores = compute_regime_scores(bars, horizon=args.horizon)
    out = args.out or "./regime_scores.json"
    save_scores(scores, out)
    print(f"\n✓ Learned regime scores saved to {out}")
    for regime, per in scores.items():
        best = max(per, key=lambda k: per[k]) if per else "-"
        print(f"  {regime.value:16s} -> best: {best} ({per})")
    print("  Set CAPYBARA_SCORES_PATH to this file to use it with the rules selector.")
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

    def _data_args(p):
        p.add_argument("--synthetic", action="store_true", help="Use synthetic data (no network).")
        p.add_argument("--symbols", default="", help="Comma-separated symbols (defaults to universe).")
        p.add_argument("--days", type=int, default=600, help="Number of days to simulate.")

    p_bt = sub.add_parser("backtest", help="Run a backtest.")
    _data_args(p_bt)
    p_bt.add_argument("--bandit", action="store_true", help="Use the trained LinUCB selector.")
    p_bt.add_argument("--model", default="", help="Path to a bandit model (.npz).")
    p_bt.set_defaults(func=cmd_backtest)

    p_train = sub.add_parser("train", help="Train the LinUCB bandit selector offline.")
    _data_args(p_train)
    p_train.add_argument("--horizon", type=int, default=10, help="Reward horizon in bars.")
    p_train.add_argument("--alpha", type=float, default=0.4, help="LinUCB exploration.")
    p_train.add_argument("--out", default="", help="Output model path (.npz).")
    p_train.set_defaults(func=cmd_train)

    p_wf = sub.add_parser("walkforward", help="Out-of-sample walk-forward validation.")
    _data_args(p_wf)
    p_wf.add_argument("--folds", type=int, default=4, help="Number of walk-forward folds.")
    p_wf.add_argument("--horizon", type=int, default=10, help="Reward horizon in bars.")
    p_wf.set_defaults(func=cmd_walkforward)

    p_attr = sub.add_parser("attribution", help="Learn the regime->strategy score table.")
    _data_args(p_attr)
    p_attr.add_argument("--horizon", type=int, default=10, help="Reward horizon in bars.")
    p_attr.add_argument("--out", default="", help="Output scores path (.json).")
    p_attr.set_defaults(func=cmd_attribution)

    p_run = sub.add_parser("run", help="Start live paper-trading loop + control API.")
    p_run.set_defaults(func=cmd_run)

    p_api = sub.add_parser("api", help="Start only the control-plane API.")
    p_api.set_defaults(func=cmd_api)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
