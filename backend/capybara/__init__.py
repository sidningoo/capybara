"""Capybara — autonomous Alpaca paper-trading bot.

A modular monolith:

    data -> features -> regime -> selector -> strategy -> risk -> execution
                                     ^                                  |
                                     |            orchestrator (loop)   |
                                     +----------------------------------+

Everything above the BrokerAdapter interface is identical in backtest and live,
which is what lets the same strategy + selector + risk code be validated offline
before it ever touches the paper account.
"""

__version__ = "0.1.0"
