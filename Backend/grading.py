# The evidence shown when a trade comes back for grading ("was my thesis
# right?"), plus the rules that keep grades honest.
#
# Before this, grading was done from memory: the review card showed the
# thesis and three buttons, nothing else. Now each due trade gets a
# scorecard with the reasons the user gave, how the price actually moved,
# how the plain S&P 500 did over the same days, and a suggested grade.
#
# Accountability rules:
#   - Returns are measured at the REVIEW DATE the user chose when they
#     wrote the thesis, not whenever they get around to grading - so you
#     can't wait for a losing trade to bounce and then call it "correct".
#   - Grading against the numbers (e.g. "correct" when the stock fell and
#     lagged the market) is allowed - the numbers don't know everything -
#     but requires a written note saying why.
#   - Each grade stores a snapshot of the numbers it was given against
#     (graded_return_pct etc.), so "which of my reasons actually make
#     money" can be answered later without re-downloading prices.
import threading
from datetime import date, datetime, timedelta, timezone
from time import monotonic

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import thesis
from deps import get_current_user, get_db
from models import Trade, User

router = APIRouter(tags=["grading"])

OUTCOMES = ("correct", "incorrect", "mixed")

# The yardstick every trade is compared against: "what if you'd just bought
# the S&P 500 that day instead?" Currency-matched, so a TSX trade is
# compared in CAD (VFV.TO) and a US trade in USD (SPY) - otherwise USD/CAD
# moves would leak into the comparison.
BENCHMARK_CAD = ("VFV.TO", "S&P 500")
BENCHMARK_USD = ("SPY", "S&P 500")
CANADIAN_SUFFIXES = (".TO", ".V", ".NE", ".CN")
# Funds that ARE the S&P 500 - comparing them to the S&P 500 says nothing,
# so they're graded on their own return.
SP500_FUNDS = {"VFV.TO", "ZSP.TO", "XUS.TO", "VSP.TO", "XSP.TO", "HXS.TO", "SPY", "VOO", "IVV", "SPLG"}

# Within this many percentage points, a move counts as "flat" - too small
# to call a thesis right or wrong.
FLAT_PCT = 2.0

# Sells made for these reasons aren't a call on the stock at all, so price
# movement afterwards can't make them right or wrong.
NOT_A_MARKET_CALL = {"need_cash", "rebalance"}

FOMO_LOOKBACK_DAYS = 10
FOMO_THRESHOLD_PCT = 8.0

MAX_SERIES_POINTS = 90

# A fill price outside this ratio of the trade day's close can't be a normal
# intraday move - it means a stock split happened since (see scorecard()).
SPLIT_RATIO_RANGE = (0.67, 1.5)


def benchmark_for(ticker: str):
    ticker = ticker.upper()
    if ticker in SP500_FUNDS:
        return None
    return BENCHMARK_CAD if ticker.endswith(CANADIAN_SUFFIXES) else BENCHMARK_USD


# --- Price history ---------------------------------------------------------------

# Daily closes don't change during the day except for today's row, so a
# short in-memory cache stops one review page (one scorecard per due trade,
# mostly sharing the same benchmark) from re-downloading the same history.
_CLOSES_TTL_SECONDS = 600
_closes_cache = {}
_closes_lock = threading.Lock()


def fetch_daily_closes(ticker: str, start: date, end: date) -> list:
    """[(date, close), ...] oldest first, for start <= date <= end. [] on failure.

    The one place this module talks to yfinance - tests replace it.
    """
    key = (ticker.upper(), start, end)
    with _closes_lock:
        hit = _closes_cache.get(key)
        if hit and monotonic() - hit[0] < _CLOSES_TTL_SECONDS:
            return hit[1]

    try:
        history = yf.Ticker(ticker.upper()).history(start=start.isoformat(), end=(end + timedelta(days=1)).isoformat())
    except Exception as e:
        print(f"yfinance history fetch failed for {ticker}: {e}")
        return []
    closes = [(ts.date(), float(close)) for ts, close in history["Close"].items() if close == close] if not history.empty else []

    with _closes_lock:
        if len(_closes_cache) > 500:
            _closes_cache.clear()
        _closes_cache[key] = (monotonic(), closes)
    return closes


def close_on_or_before(closes: list, day: date):
    """The last close on or before `day` (markets are shut on weekends/holidays)."""
    found = None
    for d, close in closes:
        if d > day:
            break
        found = (d, close)
    return found


def pct_change(start: float, end: float) -> float:
    return round((end - start) / start * 100, 2)


# --- FOMO --------------------------------------------------------------------------

def fomo_from_closes(closes_up_to_trade: list) -> dict:
    """Was the trade made right after a sharp move? Same rule main.check_fomo_for_trade
    has always used: >8% change over roughly the 5 trading days before the trade."""
    if len(closes_up_to_trade) < 2:
        return {"fomo_flag": False, "reason": "Not enough price history available to check"}

    price_at_trade = closes_up_to_trade[-1][1]
    price_before = closes_up_to_trade[max(0, len(closes_up_to_trade) - 6)][1]
    change = (price_at_trade - price_before) / price_before * 100

    if abs(change) > FOMO_THRESHOLD_PCT and change > 0:
        return {"fomo_flag": True, "reason": f"Stock rose {round(change, 2)}% in the days before this trade - possible FOMO entry"}
    if abs(change) > FOMO_THRESHOLD_PCT:
        return {"fomo_flag": True, "reason": f"Stock dropped {round(change, 2)}% in the days before this trade - possible 'buying the dip'"}
    return {"fomo_flag": False, "reason": "No significant price move detected before this trade"}


# --- Suggested grade ------------------------------------------------------------------

def _pts(value: float) -> str:
    return f"{abs(value):.1f} point{'' if abs(value) == 1 else 's'}"


def suggest_outcome(action: str, tags: list, ret: float, bench_ret, bench_label: str):
    """(outcome, plain-English reason) from the numbers, or None if price can't judge it."""
    if action == "sell":
        if tags and set(tags) <= NOT_A_MARKET_CALL:
            return None
        # A sell was right if the stock did worse afterwards than holding on
        # would have been worth - i.e. it fell, or at least lagged the market.
        if ret <= 0:
            return ("correct", f"It fell {abs(ret):.1f}% after you sold.")
        if bench_ret is not None and ret <= bench_ret:
            return ("mixed", f"It rose {ret:.1f}% after you sold, but the {bench_label} rose more ({bench_ret:+.1f}%).")
        if bench_ret is None and ret < FLAT_PCT:
            return ("mixed", f"It's roughly flat ({ret:+.1f}%) since you sold.")
        return ("incorrect", f"It rose {ret:.1f}% after you sold"
                + (f" - more than the {bench_label} ({bench_ret:+.1f}%)." if bench_ret is not None else "."))

    if bench_ret is None:
        if ret >= FLAT_PCT:
            return ("correct", f"Up {ret:.1f}% since you bought.")
        if ret <= -FLAT_PCT:
            return ("incorrect", f"Down {abs(ret):.1f}% since you bought.")
        return ("mixed", f"Roughly flat ({ret:+.1f}%) since you bought.")

    excess = ret - bench_ret
    if ret > 0 and excess >= 0:
        return ("correct", f"Up {ret:.1f}% and beat the {bench_label} by {_pts(excess)}.")
    if ret <= 0 and excess < 0:
        return ("incorrect", f"Down {abs(ret):.1f}% while the {bench_label} did {bench_ret:+.1f}%.")
    if ret > 0:
        return ("mixed", f"Made money (+{ret:.1f}%), but just buying the {bench_label} did better ({bench_ret:+.1f}%).")
    return ("mixed", f"Lost {abs(ret):.1f}%, but the {bench_label} did even worse ({bench_ret:+.1f}%).")


def contradicts(suggested, outcome: str) -> bool:
    """A grade that flatly disagrees with the numbers (not just 'mixed')."""
    return {suggested, outcome} == {"correct", "incorrect"}


# --- Scorecard -----------------------------------------------------------------------

def _downsample(points: list) -> list:
    if len(points) <= MAX_SERIES_POINTS:
        return points
    step = (len(points) - 1) / (MAX_SERIES_POINTS - 1)
    return [points[round(i * step)] for i in range(MAX_SERIES_POINTS)]


def scorecard(trade: Trade, today: date = None) -> dict:
    """Everything the review card shows for one trade. Never raises on missing data."""
    today = today or date.today()
    tags = thesis.parse_tags(trade)
    entry = float(trade.price_per_share)
    benchmark = benchmark_for(trade.ticker)
    card = {
        "trade_id": trade.id,
        "ticker": trade.ticker,
        "action": trade.action,
        "entry_price": entry,
        "trade_date": trade.trade_date.isoformat(),
        "review_date": trade.review_date.isoformat() if trade.review_date else None,
        "benchmark": {"ticker": benchmark[0], "label": benchmark[1]} if benchmark else None,
        "available": False,
    }

    closes = fetch_daily_closes(trade.ticker, trade.trade_date - timedelta(days=FOMO_LOOKBACK_DAYS), today)
    before = [c for c in closes if c[0] <= trade.trade_date]
    after = [c for c in closes if c[0] >= trade.trade_date]
    card["fomo"] = fomo_from_closes(before) if trade.action == "buy" \
        else {"fomo_flag": False, "reason": "Only buy trades are checked for FOMO"}

    if not after or entry <= 0:
        card["message"] = f"No price history for {trade.ticker} since this trade, so it can only be graded from memory."
        return card

    # yfinance history is split-adjusted but the recorded fill price isn't:
    # after a 5:1 split the trade-day close shows ~1/5 of what was paid,
    # which would read as a fake -80%. If the fill and that day's close are
    # wildly apart, measure from the (adjusted) close instead.
    trade_day_close = close_on_or_before(closes, trade.trade_date) or after[0]
    if not SPLIT_RATIO_RANGE[0] <= entry / trade_day_close[1] <= SPLIT_RATIO_RANGE[1]:
        entry = trade_day_close[1]
        card["split_adjusted"] = True

    bench_closes = fetch_daily_closes(benchmark[0], trade.trade_date - timedelta(days=FOMO_LOOKBACK_DAYS), today) if benchmark else []
    bench_start = close_on_or_before(bench_closes, trade.trade_date) if bench_closes else None

    def bench_return(day):
        if not bench_start:
            return None
        bench_end = close_on_or_before(bench_closes, day)
        return pct_change(bench_start[1], bench_end[1]) if bench_end else None

    last_day, last_close = after[-1]
    card.update({
        "available": True,
        "as_of": last_day.isoformat(),
        "price_now": round(last_close, 4),
        "return_now_pct": pct_change(entry, last_close),
        "benchmark_return_now_pct": bench_return(last_day),
        "best_pct": pct_change(entry, max(c for _, c in after)),
        "worst_pct": pct_change(entry, min(c for _, c in after)),
        "series": [{"date": d.isoformat(), "close": round(c, 4)} for d, c in _downsample(after)],
    })
    if benchmark and card["benchmark_return_now_pct"] is None:
        card["benchmark"] = None  # benchmark history failed - grade on the stock alone

    # Judge at the review date the user committed to, if it has passed and
    # there's a close for it; otherwise (graded early) as of today.
    at_review = close_on_or_before(after, trade.review_date) if trade.review_date and trade.review_date <= last_day else None
    if at_review:
        card["at_review"] = {"date": at_review[0].isoformat(), "price": round(at_review[1], 4),
                             "return_pct": pct_change(entry, at_review[1]),
                             "benchmark_return_pct": bench_return(at_review[0])}
        judged_return, judged_bench, card["judged_at"] = card["at_review"]["return_pct"], card["at_review"]["benchmark_return_pct"], "review_date"
    else:
        card["at_review"] = None
        judged_return, judged_bench, card["judged_at"] = card["return_now_pct"], card["benchmark_return_now_pct"], "now"

    if not card["benchmark"]:
        judged_bench = None
    card["return_pct"] = judged_return
    card["benchmark_return_pct"] = judged_bench
    card["excess_pct"] = round(judged_return - judged_bench, 2) if judged_bench is not None else None

    suggestion = suggest_outcome(trade.action, tags, judged_return, judged_bench, benchmark[1] if card["benchmark"] else "")
    card["suggestion"] = {"outcome": suggestion[0], "reason": suggestion[1]} if suggestion else None
    if not suggestion and trade.action == "sell":
        card["suggestion_note"] = "You sold for cash or rebalancing - that's not a call on the stock, so price alone can't grade it."
    return card


# --- Routes ------------------------------------------------------------------------

def _own_trade(db: Session, user: User, trade_id: int) -> Trade:
    trade = db.query(Trade).filter(Trade.id == trade_id, Trade.user_id == user.id).first()
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade with id {trade_id} not found")
    return trade


# Loaded per review card (not inside GET /thesis-reviews) so the list shows
# instantly and each card fills in its numbers as its prices arrive.
@router.get("/thesis-reviews/{trade_id}/scorecard")
def get_scorecard(trade_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return scorecard(_own_trade(db, current_user, trade_id))


def apply_grade(db: Session, user: User, trade_id: int, outcome: str, notes) -> Trade:
    """Saves a grade plus the snapshot of numbers it was made against."""
    if outcome not in OUTCOMES:
        raise HTTPException(status_code=400, detail=f"outcome_tag must be one of: {', '.join(OUTCOMES)}")
    trade = _own_trade(db, user, trade_id)
    notes = (notes or "").strip() or None

    card = scorecard(trade)
    suggested = (card.get("suggestion") or {}).get("outcome")
    if contradicts(suggested, outcome) and not notes:
        raise HTTPException(
            status_code=400,
            detail=f"The numbers say \"{suggested}\" ({card['suggestion']['reason']}) - "
                   f"add a note explaining why you're grading it \"{outcome}\".",
        )

    trade.outcome_tag = outcome
    trade.review_notes = notes
    trade.graded_at = datetime.now(timezone.utc).replace(tzinfo=None)
    trade.suggested_outcome = suggested
    trade.graded_return_pct = card.get("return_pct")
    trade.graded_benchmark_return_pct = card.get("benchmark_return_pct")
    db.commit()
    return trade


def describe_grade(trade: Trade) -> str:
    """A graded trade's outcome as a phrase for the advisor's trade list."""
    if not trade.outcome_tag:
        return "not yet reviewed"
    text = trade.outcome_tag
    if trade.graded_return_pct is not None:
        text += f" ({trade.graded_return_pct:+.1f}%"
        if trade.graded_benchmark_return_pct is not None:
            text += f" vs S&P 500 {trade.graded_benchmark_return_pct:+.1f}%"
        text += ")"
    if contradicts(trade.suggested_outcome, trade.outcome_tag):
        text += f" - graded against the numbers, which said {trade.suggested_outcome}"
    return text
