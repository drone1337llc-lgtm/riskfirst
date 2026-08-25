"""CLI entrypoint for the Alpaca options agent.

Usage (paper-only):
    python -m options.agent                 # dry-run with MockClient, logs to decisions.db
    ALPACA_IS_LIVE=1 python -m options.agent  # real Alpaca MCP (paper keys required)

Runs one decision cycle and prints the executed actions.
"""
import json
import sys

from . import config, agent


def main() -> int:
    config.validate_paper_config()   # refuses live; checks Level 3
    a = agent.Agent(db_path="decisions.db")
    try:
        decisions = a.run_cycle()
        print(json.dumps(decisions, indent=2))
        print(f"\nExecuted {len(decisions)} action(s). Log -> decisions.db")
        return 0
    finally:
        a.close()


if __name__ == "__main__":
    sys.exit(main())
