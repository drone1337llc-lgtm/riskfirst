"""Alpaca crypto bars + feature engineering (no API keys needed for data)."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

import config

_client = CryptoHistoricalDataClient()


def fetch_bars(symbol: str, bars: int = config.LOOKBACK_BARS) -> pd.DataFrame:
    """Fetch recent bars for one symbol as an OHLCV DataFrame."""
    tf = TimeFrame(config.BAR_MINUTES, TimeFrameUnit.Minute)
    start = datetime.now(timezone.utc) - timedelta(minutes=config.BAR_MINUTES * (bars + 10))
    req = CryptoBarsRequest(symbol_or_symbols=[symbol], timeframe=tf, start=start)
    df = _client.get_crypto_bars(req).df
    df = df.xs(symbol, level="symbol") if "symbol" in df.index.names else df
    return df[["open", "high", "low", "close", "volume"]].tail(bars)


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def make_features(asset: pd.DataFrame, btc: pd.DataFrame) -> pd.DataFrame:
    """Feature frame shared by the training env and the live loop."""
    f = pd.DataFrame(index=asset.index)
    c = asset["close"]
    f["ret_1"] = c.pct_change()
    f["ret_4"] = c.pct_change(4)
    f["ret_24"] = c.pct_change(24)
    f["rsi"] = _rsi(c) / 100.0
    ema_f, ema_s = c.ewm(span=12).mean(), c.ewm(span=26).mean()
    f["macd"] = (ema_f - ema_s) / c
    f["vol_z"] = (asset["volume"] - asset["volume"].rolling(96).mean()) / (
        asset["volume"].rolling(96).std() + 1e-9)
    f["hl_range"] = (asset["high"] - asset["low"]) / c
    f["volat_24"] = f["ret_1"].rolling(24).std()
    btc_c = btc["close"].reindex(asset.index).ffill()
    f["btc_ret_1"] = btc_c.pct_change()
    f["btc_ret_24"] = btc_c.pct_change(24)
    f["btc_rsi"] = _rsi(btc_c) / 100.0
    return f.replace([np.inf, -np.inf], np.nan).dropna()


def load_dataset() -> tuple:
    """Returns (price df aligned to features, feature df)."""
    asset = fetch_bars(config.SYMBOL)
    btc = fetch_bars(config.CONTEXT_SYMBOL)
    feats = make_features(asset, btc)
    return asset.loc[feats.index], feats
