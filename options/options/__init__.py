"""Alpaca Options Agent — autonomous paper options-trading scaffold.

Architecture (multi-agent):
  bull / bear / neutral  -> strategy "sub-agents" (strategies.py)
  risk arbiter          -> agent.py gates every idea against hard limits
  IV-rank structure     -> options.py scores chains to pick the best structure

All I/O to Alpaca runs through client.py, which is mocked for offline tests
and wired to the real MCP server behind the LIVE flag.
"""

from . import config, options, strategies, client, agent

__all__ = ["config", "options", "strategies", "client", "agent"]
__version__ = "0.1.0"
