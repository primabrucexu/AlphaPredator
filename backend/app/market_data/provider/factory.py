from __future__ import annotations

from threading import Lock

from .thsdk import ThsdkMarketDataProvider


_provider: ThsdkMarketDataProvider | None = None
_provider_lock = Lock()


def get_process_market_provider() -> ThsdkMarketDataProvider:
    global _provider
    with _provider_lock:
        if _provider is None:
            _provider = ThsdkMarketDataProvider()
        return _provider


def close_process_market_provider() -> None:
    global _provider
    with _provider_lock:
        if _provider is not None:
            _provider.close()
            _provider = None
