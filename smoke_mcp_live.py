"""End-to-end smoke of McpClient against the REAL alpaca-mcp-server binary.

Dummy paper keys: the server boots + initializes, and API calls fail with an
auth error surfaced through our MCPError path (proving the wire path works).
Run from repo root with the venv python.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "options"))

from options import client as cl  # noqa: E402

os.environ["ALPACA_API_KEY"] = "PKDUMMY00000000000000"
os.environ["ALPACA_SECRET_KEY"] = "dummysecret123"
os.environ["ALPACA_IS_LIVE"] = "1"

c = cl.McpClient()
try:
    print("server:", c._server)
    print("get_account ->")
    try:
        acct = c.get_account()
        print("  OK:", acct)
    except cl.MCPError as e:
        print("  MCPError (expected w/ dummy keys):", str(e)[:200])
    print("get_contracts ->")
    try:
        chain = c.get_contracts("SPY")
        print("  OK: %d contracts" % len(chain))
    except cl.MCPError as e:
        print("  MCPError (expected w/ dummy keys):", str(e)[:200])
finally:
    c.close()
print("SMOKE DONE")
