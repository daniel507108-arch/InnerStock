# The "why did you make this trade?" inbox, plus the summary of WHY a user
# trades that feeds the advisor.
#
# InnerStock's core rule is that every trade needs a thesis. Trades logged
# by hand get one up front; trades synced from a brokerage arrive without
# one, so they land here until the user answers. Two accountability rules:
#   - Answers are final. Once a trade has a reason it can't be rewritten -
#     otherwise it's too easy to "remember" a better reason after seeing
#     how the trade turned out.
#   - "Don't remember" is a real answer, not a skip. How often someone can't
#     say why they traded is itself one of the most telling patterns.
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from deps import get_current_user, get_db
from models import BrokerageAccount, Trade, User

router = APIRouter(prefix="/trades", tags=["thesis"])

DONT_REMEMBER = "dont_remember"

BUY_REASONS = {
    "long_term": "Long-term conviction",
    "valuation": "Looked undervalued",
    "dip_buy": "Bought the dip",
    "news_earnings": "Earnings / news",
    "momentum": "Momentum / chart",
    "dca": "Regular investing (DCA)",
    "speculation": "Speculative bet",
    "tip_social": "Tip / social media",
    "fomo": "Fear of missing out",
    DONT_REMEMBER: "Don't remember",
}

SELL_REASONS = {
    "take_profit": "Took profits",
    "stop_loss": "Cut losses",
    "thesis_broken": "Thesis broke",
    "rebalance": "Rebalancing",
    "better_opportunity": "Better opportunity elsewhere",
    "need_cash": "Needed the cash",
    "panic": "Panic / fear",
    DONT_REMEMBER: "Don't remember",
}

# A reason written more than this long after the trade is flagged as
# hindsight - memory of "why" drifts once you know how the trade went.
HINDSIGHT_AFTER = timedelta(days=7)

MIN_THESIS_LENGTH = 10


def reasons_for(action: str) -> dict:
    return BUY_REASONS if action == "buy" else SELL_REASONS


def label_for(action: str, tag: str) -> str:
    return reasons_for(action).get(tag, tag)


def parse_tags(trade: Trade) -> list[str]:
    return [t for t in (trade.reason_tags or "").split(",") if t]


def validate_tags(action: str, tags: list[str]) -> list[str]:
    """Checks reason tags against the catalog for this action. Raises 400."""
    tags = list(dict.fromkeys(t.strip() for t in tags if t.strip()))  # dedupe, keep order
    allowed = reasons_for(action)
    unknown = [t for t in tags if t not in allowed]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Not a valid reason for a {action}: {', '.join(unknown)}")
    if DONT_REMEMBER in tags and len(tags) > 1:
        raise HTTPException(status_code=400, detail="\"Don't remember\" can't be combined with other reasons")
    return tags


def needs_reason_filter(user: User):
    return (Trade.user_id == user.id, Trade.thesis_text.is_(None), Trade.reason_tags.is_(None))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _traded_at(trade: Trade) -> datetime:
    return datetime.combine(trade.trade_date, trade.trade_time or time(0, 0))


def is_hindsight(trade: Trade) -> bool:
    return bool(trade.thesis_written_at) and trade.thesis_written_at - _traded_at(trade) > HINDSIGHT_AFTER


# --- Endpoints ---------------------------------------------------------------------

# The reason catalog - the frontend renders its chips from this, so the
# list lives in exactly one place.
@router.get("/reasons")
def get_reason_catalog(current_user: User = Depends(get_current_user)):
    def as_list(catalog):
        return [{"tag": tag, "label": label} for tag, label in catalog.items()]
    return {"buy": as_list(BUY_REASONS), "sell": as_list(SELL_REASONS)}


@router.get("/needs-thesis/count")
def count_needing_thesis(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"count": db.query(Trade).filter(*needs_reason_filter(current_user)).count()}


# Every trade still waiting for a reason, newest first (recent trades are
# the ones the user can still remember accurately).
@router.get("/needs-thesis")
def list_needing_thesis(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (
        db.query(Trade, BrokerageAccount.name)
        .outerjoin(BrokerageAccount, BrokerageAccount.id == Trade.brokerage_account_id)
        .filter(*needs_reason_filter(current_user))
        .order_by(Trade.trade_date.desc(), Trade.trade_time.desc(), Trade.id.desc())
        .all()
    )
    return {
        "count": len(rows),
        "trades": [
            {
                "id": t.id,
                "ticker": t.ticker,
                "action": t.action,
                "quantity": float(t.quantity),
                "price_per_share": float(t.price_per_share),
                "trade_date": t.trade_date.isoformat(),
                "trade_time": t.trade_time.isoformat() if t.trade_time else None,
                "source": t.source,
                "account": account_name,
            }
            for t, account_name in rows
        ],
    }


class ThesisAnswer(BaseModel):
    # One trade, or several with the same answer (e.g. a run of identical
    # DCA buys) - they must all be the same action (buy or sell).
    trade_ids: List[int] = Field(min_length=1, max_length=500)
    reason_tags: List[str] = Field(min_length=1)
    thesis_text: Optional[str] = None
    conviction_score: Optional[int] = Field(default=None, ge=1, le=5)
    review_date: Optional[date] = None


@router.put("/thesis")
def answer_thesis(answer: ThesisAnswer, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    trade_ids = list(dict.fromkeys(answer.trade_ids))
    trades = db.query(Trade).filter(Trade.user_id == current_user.id, Trade.id.in_(trade_ids)).all()
    # All-or-nothing: any id that isn't this user's trade rejects the whole
    # request, without revealing whether that id exists for someone else.
    if len(trades) != len(trade_ids):
        raise HTTPException(status_code=404, detail="One or more trades not found")

    actions = {t.action for t in trades}
    if len(actions) > 1:
        raise HTTPException(status_code=400, detail="Buys and sells need separate answers")
    action = actions.pop()

    already = [t.id for t in trades if t.thesis_text is not None or t.reason_tags is not None]
    if already:
        raise HTTPException(status_code=409, detail=f"Trade(s) {already} already have a reason - answers are final")

    tags = validate_tags(action, answer.reason_tags)
    if not tags:
        raise HTTPException(status_code=400, detail="Pick at least one reason")

    thesis_text = (answer.thesis_text or "").strip() or None
    if tags != [DONT_REMEMBER]:
        if not thesis_text or len(thesis_text) < MIN_THESIS_LENGTH:
            raise HTTPException(status_code=400, detail=f"Write a short thesis (at least {MIN_THESIS_LENGTH} characters)")
        if answer.conviction_score is None:
            raise HTTPException(status_code=400, detail="Rate how confident you were (1-5)")

    written_at = _utcnow()
    for trade in trades:
        trade.reason_tags = ",".join(tags)
        trade.thesis_text = thesis_text
        trade.conviction_score = answer.conviction_score
        trade.review_date = answer.review_date
        trade.thesis_written_at = written_at
    db.commit()

    return {"updated": [t.id for t in trades],
            "remaining": db.query(Trade).filter(*needs_reason_filter(current_user)).count()}


@router.get("/reasons-summary")
def get_reasons_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return reasons_summary(db, current_user)


# --- Summary (also used by the advisor's context) ------------------------------------

def reasons_summary(db: Session, user: User) -> dict:
    """How this user explains their trades, and how each reason has worked out."""
    trades = db.query(Trade).filter(Trade.user_id == user.id).all()
    answered = [t for t in trades if t.reason_tags]
    needs_reason = [t for t in trades if t.thesis_text is None and t.reason_tags is None]

    stats = {}
    for trade in answered:
        for tag in parse_tags(trade):
            key = (trade.action, tag)
            entry = stats.setdefault(key, {"action": trade.action, "tag": tag, "label": label_for(trade.action, tag),
                                           "count": 0, "convictions": [], "correct": 0, "incorrect": 0, "mixed": 0})
            entry["count"] += 1
            if trade.conviction_score is not None:
                entry["convictions"].append(trade.conviction_score)
            if trade.outcome_tag in ("correct", "incorrect", "mixed"):
                entry[trade.outcome_tag] += 1

    by_reason = []
    for entry in sorted(stats.values(), key=lambda e: (-e["count"], e["tag"])):
        graded = entry["correct"] + entry["incorrect"] + entry["mixed"]
        convictions = entry.pop("convictions")
        by_reason.append({
            **entry,
            "avg_conviction": round(sum(convictions) / len(convictions), 1) if convictions else None,
            "graded": graded,
            "correct_rate": round(entry["correct"] / graded * 100, 1) if graded else None,
        })

    dont_remember = sum(1 for t in answered if parse_tags(t) == [DONT_REMEMBER])
    hindsight = sum(1 for t in answered if is_hindsight(t))
    return {
        "total_trades": len(trades),
        "answered": len(answered),
        "needs_reason": len(needs_reason),
        "by_reason": by_reason,
        "dont_remember_count": dont_remember,
        "dont_remember_rate": round(dont_remember / len(answered) * 100, 1) if answered else 0,
        "hindsight_count": hindsight,
        "hindsight_rate": round(hindsight / len(answered) * 100, 1) if answered else 0,
    }


def advisor_context_section(db: Session, user: User) -> str:
    """The "why this user trades" block of the advisor's system prompt."""
    summary = reasons_summary(db, user)
    if not summary["answered"]:
        return (f"The user hasn't given reasons for any trades yet "
                f"({summary['needs_reason']} trades are waiting for a reason).")

    def line(entry):
        text = f"- {entry['label']}: {entry['count']} trade(s)"
        if entry["avg_conviction"] is not None:
            text += f", avg conviction {entry['avg_conviction']}/5"
        if entry["graded"]:
            text += f", {entry['graded']} graded, {entry['correct_rate']}% correct"
        return text

    buys = [line(e) for e in summary["by_reason"] if e["action"] == "buy"]
    sells = [line(e) for e in summary["by_reason"] if e["action"] == "sell"]
    parts = [
        f"Reasons given for {summary['answered']} of {summary['total_trades']} trades "
        f"({summary['needs_reason']} still unanswered).",
        "Why they BUY:", *(buys or ["- no buys answered yet"]),
        "Why they SELL:", *(sells or ["- no sells answered yet"]),
        f"Couldn't remember why: {summary['dont_remember_count']} trade(s) ({summary['dont_remember_rate']}% of answered).",
        f"Reasons written in hindsight (over {HINDSIGHT_AFTER.days} days after the trade): "
        f"{summary['hindsight_count']} ({summary['hindsight_rate']}%) - treat these as less reliable.",
    ]
    return "\n".join(parts)


def describe_trade_reason(trade: Trade) -> str:
    """One trade's reasoning, as a phrase for the advisor's trade list."""
    tags = parse_tags(trade)
    if not tags and trade.thesis_text is None:
        return "no reason given yet"
    parts = []
    if tags:
        parts.append("reasons: " + ", ".join(label_for(trade.action, t) for t in tags))
    if trade.thesis_text:
        parts.append(f"thesis: \"{trade.thesis_text}\"")
    if is_hindsight(trade):
        parts.append("(written in hindsight)")
    return "; ".join(parts)
