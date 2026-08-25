"""TensorTrade environment: target-allocation actions + drawdown-penalized reward."""
import numpy as np
from gym.spaces import Discrete

import tensortrade.env.default as default
from tensortrade.env.default.actions import TensorTradeActionScheme
from tensortrade.env.default.rewards import TensorTradeRewardScheme
from tensortrade.feed.core import DataFeed, Stream
from tensortrade.oms.exchanges import Exchange, ExchangeOptions
from tensortrade.oms.instruments import Instrument, USD
from tensortrade.oms.orders import proportion_order
from tensortrade.oms.services.execution.simulated import execute_order
from tensortrade.oms.wallets import Portfolio, Wallet

import config

ASSET = Instrument(config.SYMBOL.split("/")[0], 8, config.SYMBOL.split("/")[0])


class TargetAllocation(TensorTradeActionScheme):
    """Discrete actions = target exposure fractions. Mirrors live execution exactly."""

    registered_name = "target-allocation"

    def __init__(self, cash_wallet, asset_wallet, targets=config.TARGET_ALLOCATIONS):
        super().__init__()
        self.cash = cash_wallet
        self.asset = asset_wallet
        self.targets = targets

    @property
    def action_space(self):
        return Discrete(len(self.targets))

    def _price(self) -> float:
        return float(self.cash.exchange.quote_price(USD / ASSET))

    def get_orders(self, action, portfolio):
        target = self.targets[int(action)]
        nw = float(portfolio.net_worth)
        asset_val = float(self.asset.total_balance.as_float()) * self._price()
        delta = target * nw - asset_val
        if abs(delta) < max(config.MIN_ORDER_NOTIONAL, 0.005 * nw):
            return []
        if delta > 0:
            cash_bal = float(self.cash.balance.as_float())
            if cash_bal <= config.MIN_ORDER_NOTIONAL:
                return []
            prop = min(1.0, delta / cash_bal)
        else:
            if asset_val <= config.MIN_ORDER_NOTIONAL:
                return []
            prop = min(1.0, -delta / asset_val)
        src, dst = (self.cash, self.asset) if delta > 0 else (self.asset, self.cash)
        try:
            return [proportion_order(portfolio, src, dst, prop)]
        except Exception:
            return []


class DrawdownPenalizedReturns(TensorTradeRewardScheme):
    """Log-return of net worth minus a penalty each time max drawdown deepens."""

    registered_name = "dd-penalized"

    def __init__(self, lam: float = config.DRAWDOWN_LAMBDA):
        super().__init__()
        self.lam = lam
        self.reset()

    def reset(self):
        self.prev_nw = None
        self.peak = None
        self.max_dd = 0.0

    def get_reward(self, portfolio) -> float:
        nw = float(portfolio.net_worth)
        if self.prev_nw is None:
            self.prev_nw, self.peak = nw, nw
            return 0.0
        r = float(np.log(max(nw, 1e-9) / max(self.prev_nw, 1e-9)))
        self.prev_nw = nw
        self.peak = max(self.peak, nw)
        dd = (self.peak - nw) / self.peak if self.peak > 0 else 0.0
        penalty = self.lam * max(0.0, dd - self.max_dd)
        self.max_dd = max(self.max_dd, dd)
        return r - penalty


def build_env(prices, feats, window_size: int = config.WINDOW_SIZE):
    """Create a TensorTrade TradingEnv from aligned price/feature DataFrames."""
    price_stream = Stream.source(prices["close"].tolist(), dtype="float").rename(
        f"USD-{ASSET.symbol}")
    exchange = Exchange("sim", service=execute_order,
                        options=ExchangeOptions(commission=config.COMMISSION))(price_stream)

    cash = Wallet(exchange, config.INITIAL_CASH * USD)
    asset = Wallet(exchange, 0 * ASSET)
    portfolio = Portfolio(USD, [cash, asset])

    feed = DataFeed([
        Stream.source(feats[c].tolist(), dtype="float").rename(c) for c in feats.columns
    ])
    feed.compile()

    return default.create(
        portfolio=portfolio,
        action_scheme=TargetAllocation(cash, asset),
        reward_scheme=DrawdownPenalizedReturns(),
        feed=feed,
        window_size=window_size,
        max_allowed_loss=0.5,
    )
