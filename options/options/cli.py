"""CLI entrypoint for the Alpaca options agent.

Usage (paper-only):
    python -m options.agent                  # MockClient dry-run + LLM referee (local Ollama)
    ALPACA_IS_LIVE=1 python -m options.agent # real Alpaca MCP (paper keys required)

Runs one decision cycle and prints the executed actions.

The LLM referee (options/llm_referee.py) reviews every accepted proposal and
its verdict is written to the decision log as part of the audit trail. It
calls local Ollama (OLLAMA_URL/OLLAMA_MODEL env, default qwen2.5:1.5b) and
fails open on any outage. By default it is ADVISORY ONLY — deterministic risk
gates in code are the enforcement layer. Set OLLAMA_REFEREE_ENFORCE=1 to let
the LLM veto proposals, or --no-referee to disable it entirely.
"""
import json
import os
import sys

from . import config, agent
from .llm_referee import LLMReferee


def main() -> int:
    config.validate_paper_config()   # refuses live; checks Level 3
    use_referee = not (
        os.environ.get("OLLAMA_REFEREE_DISABLED", "0") == "1"
        or "--no-referee" in sys.argv
    )
    referee = LLMReferee() if use_referee else None
    a = agent.Agent(db_path="decisions.db", referee=referee)
    try:
        decisions = a.run_cycle()
        print(json.dumps(decisions, indent=2))
        print(f"\nExecuted {len(decisions)} action(s). Log -> decisions.db")
        if referee is not None:
            mode = "ENFORCE" if referee.enforce else "advisory"
            print(f"LLM referee: {referee.model} via {referee.url} ({mode})")
        return 0
    finally:
        a.close()


if __name__ == "__main__":
    sys.exit(main())
