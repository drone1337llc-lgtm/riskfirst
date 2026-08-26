"""Central config for the crypto RL bot."""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Market ---
# Override per instance: CRYPTOBOT_SYMBOL=SOL-USD (systemd template passes %i)
SYMBOL = os.getenv("CRYPTOBOT_SYMBOL", "ETH-USD").replace("-", "/")
CONTEXT_SYMBOL = "BTC/USD"  # always observed (crypto correlation)
BAR_MINUTES = 1
LOOKBACK_BARS = 50000        # history pulled for features/warmup

# --- Agent / env ---
TARGET_ALLOCATIONS = (0.0, 0.25, 0.5, 0.75, 1.0)  # discrete target exposure
WINDOW_SIZE = 500            # observation window (bars)
COMMISSION = 0.0         # Alpaca paper charges ZERO commission; keep train=live per council verdict 2026-08-24
DRAWDOWN_LAMBDA = 0.4       # council verdict 2026-08-24: 3.0 dominated reward, forced cash-hugging
INITIAL_CASH = 10_000

# --- Live loop ---
DECISION_INTERVAL_S = 300  # council verdict: act every 5min live, keep 1-min train bars
MACRO_INTERVAL_S = 60      # query LLM regime hourly
MIN_ORDER_NOTIONAL = 10.0       # skip dust rebalances
_SYM = SYMBOL.replace("/", "")
CHECKPOINT_PATH = os.path.join(os.path.dirname(__file__), "checkpoints", f"ppo_{_SYM}.zip")
CHALLENGER_PATH = os.path.join(os.path.dirname(__file__), "checkpoints", f"ppo_{_SYM}_challenger.zip")
STATE_DIR = os.path.join(os.path.dirname(__file__), "state", _SYM)
os.makedirs(STATE_DIR, exist_ok=True)

# --- Services ---
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")

assert ALPACA_PAPER, "Live trading is disabled. Set ALPACA_PAPER=true."
