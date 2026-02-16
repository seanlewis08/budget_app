"""
Live stock price fetcher using yfinance.
Updates Security.close_price for all tickers in the investments database.
"""

import logging
from datetime import datetime, time
import pytz

logger = logging.getLogger(__name__)


def is_market_open() -> bool:
    """Check if US stock market is currently open (9:30-16:00 ET, weekdays)."""
    et = pytz.timezone("US/Eastern")
    now = datetime.now(et)
    if now.weekday() >= 5:  # Saturday, Sunday
        return False
    market_open = time(9, 30)
    market_close = time(16, 0)
    return market_open <= now.time() <= market_close


def fetch_price_for_ticker(ticker: str) -> float | None:
    """Fetch the current price for a single ticker. Returns None on failure."""
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        data = yf.download(ticker, period="1d", progress=False)
        close_col = data.get("Close")
        if close_col is not None and len(close_col) > 0:
            price = float(close_col.iloc[-1])
            return price if price > 0 else None
    except Exception:
        return None
    return None


def fetch_all_prices(inv_db) -> dict:
    """
    Fetch current prices for all securities with tickers using yfinance.
    Updates close_price and close_price_as_of in the database.
    Returns: {"updated": int, "failed": int, "tickers": {ticker: price}}
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed — skipping price fetch. Run: pip install yfinance")
        return {"updated": 0, "failed": 0, "tickers": {}}

    from ..models_investments import Security

    # Get all securities with tickers
    securities = inv_db.query(Security).filter(
        Security.ticker.isnot(None),
        Security.ticker != "",
        Security.security_type != "cash_equivalent",
    ).all()

    if not securities:
        return {"updated": 0, "failed": 0, "tickers": {}}

    ticker_map = {}  # ticker -> [Security, ...]
    for sec in securities:
        ticker = sec.ticker.upper().strip()
        if ticker not in ticker_map:
            ticker_map[ticker] = []
        ticker_map[ticker].append(sec)

    tickers = list(ticker_map.keys())
    logger.info(f"Fetching prices for {len(tickers)} tickers: {tickers[:10]}...")

    updated = 0
    failed = 0
    price_results = {}

    try:
        # Batch fetch — yfinance handles multiple tickers efficiently
        data = yf.download(tickers, period="1d", progress=False, threads=True)

        # Handle single vs multiple tickers
        if len(tickers) == 1:
            ticker = tickers[0]
            close_col = data.get("Close")
            if close_col is not None and len(close_col) > 0:
                price = float(close_col.iloc[-1])
                if price > 0:
                    for sec in ticker_map[ticker]:
                        sec.close_price = price
                        sec.close_price_as_of = datetime.utcnow()
                        sec.price_source = "yfinance"
                    price_results[ticker] = price
                    updated += 1
        else:
            close_data = data.get("Close")
            if close_data is not None:
                for ticker in tickers:
                    try:
                        col = close_data.get(ticker) if hasattr(close_data, "get") else close_data[ticker]
                        if col is not None and len(col) > 0:
                            price = float(col.iloc[-1])
                            if price > 0:
                                for sec in ticker_map[ticker]:
                                    sec.close_price = price
                                    sec.close_price_as_of = datetime.utcnow()
                                    sec.price_source = "yfinance"
                                price_results[ticker] = price
                                updated += 1
                            else:
                                failed += 1
                        else:
                            failed += 1
                    except Exception as e:
                        logger.warning(f"Failed to get price for {ticker}: {e}")
                        failed += 1

    except Exception as e:
        logger.error(f"yfinance batch download failed: {e}")
        failed = len(tickers)

    inv_db.commit()
    logger.info(f"Price fetch complete: {updated} updated, {failed} failed")
    return {"updated": updated, "failed": failed, "tickers": price_results}
