from sqlalchemy import Boolean, Column, Integer, String, Numeric, Date, DateTime, ForeignKey, Text, Time, UniqueConstraint
from sqlalchemy.sql import false, func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    # Required multiple-choice fields
    risk_tolerance = Column(String, nullable=False)      # e.g. "low", "medium", "high"
    investing_goals = Column(String, nullable=False)     # e.g. "growth", "income", "preservation", "speculation"
    trading_style = Column(String, nullable=False)        # multi-select, comma-separated e.g. "buy_and_hold,swing" - same pattern as sectors_of_interest below
    time_horizon = Column(String, nullable=False)        # e.g. "under_1y", "1_to_5y", "5y_plus"
    income_bracket = Column(String, nullable=False)      # e.g. "under_50k", "50k_100k", "100k_plus"
    experience_level = Column(String, nullable=False)    # e.g. "beginner", "intermediate", "experienced"
    sectors_of_interest = Column(String, nullable=False) # comma-separated, e.g. "tech,healthcare"

    # Optional free-text field - nullable, never required, never crashes
    # on empty submission.
    biggest_fear = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
#THE TRADE OBJECT 
class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ticker = Column(String, nullable=False)
    action = Column(String, nullable=False)          # "buy" or "sell"
    quantity = Column(Numeric, nullable=False)
    price_per_share = Column(Numeric, nullable=False)
    trade_date = Column(Date, nullable=False)
    # NEW - required when logging a trade manually via POST /trades (see
    # TradeCreate), to pin down which intraday price bar to auto-fill
    # price_per_share with at log time (see /stock/{ticker}/price-at).
    # Nullable at the DB level anyway, since CSV-imported trades (see
    # import_trades_wealthsimple) never have a time and build Trade rows
    # directly, bypassing TradeCreate's validation entirely - and every
    # trade imported before this feature existed has no time on record.
    # Assumed to be US/Eastern market time - both US tickers and .TO (TSX)
    # tickers trade on that clock.
    trade_time = Column(Time, nullable=True)
    thesis_text = Column(Text, nullable=True)
    conviction_score = Column(Integer, nullable=True)   # 1-5
    review_date = Column(Date, nullable=True)
    outcome_tag = Column(String, nullable=True)       # stays empty until resurfaced & graded
    review_notes = Column(Text, nullable=True)         # NEW — optional freeform reflection, added at grading time
    created_at = Column(DateTime, server_default=func.now())

    # Where this trade came from: "manual" (logged through POST /trades),
    # "csv" (the old Wealthsimple CSV import, since removed) or "snaptrade"
    # (synced from a linked brokerage account - see snaptrade_sync.py).
    source = Column(String, nullable=False, server_default="manual")
    # The brokerage's own id for this trade (SnapTrade activity id). Unique
    # per user, which is what makes re-running a sync safe: a trade that's
    # already been imported is recognised and skipped, never duplicated.
    # Null for manual/csv trades.
    external_id = Column(String, nullable=True)
    # Which linked account (TFSA, personal, ...) a synced trade happened in.
    brokerage_account_id = Column(Integer, ForeignKey("brokerage_accounts.id"), nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "external_id", name="uq_trades_user_external_id"),)


class PriceCache(Base):
    __tablename__ = "price_cache"

    ticker = Column(String, primary_key=True)
    current_price = Column(Numeric, nullable=False)
    previous_close = Column(Numeric, nullable=True)
    market_cap = Column(Numeric, nullable=True)
    pe_ratio = Column(Numeric, nullable=True)
    sector = Column(String, nullable=True)
    # NEW - fundamentals for the advisor chat, same yfinance .info call as
    # everything else above so there's no extra API cost to pull these.
    forward_pe = Column(Numeric, nullable=True)
    price_to_book = Column(Numeric, nullable=True)
    profit_margins = Column(Numeric, nullable=True)
    revenue_growth = Column(Numeric, nullable=True)
    debt_to_equity = Column(Numeric, nullable=True)
    dividend_yield = Column(Numeric, nullable=True)
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())

class SentimentCache(Base):
    __tablename__ = "sentiment_cache"

    # Same shape/purpose as PriceCache above, but for Claude sentiment
    # analysis instead of yfinance prices - keyed by ticker, refreshed on a
    # TTL instead of every request, since re-generating this means a real
    # Claude API call (unlike a price lookup, this one costs money per hit).
    ticker = Column(String, primary_key=True)
    sentiment = Column(String, nullable=False)     # "positive" / "neutral" / "negative"
    summary = Column(Text, nullable=False)
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String, nullable=False)     # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ticker = Column(String, nullable=False)
    added_at = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "ticker", name="uq_watchlist_user_ticker"),)


class BrokerageAccount(Base):
    __tablename__ = "brokerage_accounts"

    # One row per brokerage account linked through SnapTrade (e.g. a
    # Wealthsimple TFSA). Created/updated by snaptrade_sync.sync_accounts.
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    external_account_id = Column(String, nullable=False)   # SnapTrade's account id
    institution = Column(String, nullable=True)            # e.g. "Wealthsimple Trade"
    name = Column(String, nullable=True)                   # e.g. "Wealthsimple Trade TFSA"
    account_type = Column(String, nullable=True)           # e.g. "tfsa", "non_registered", "non_registered_crypto"
    # Only accounts with this on have their trades pulled in. Defaults are
    # set per account type when the account is first seen (see
    # snaptrade_sync.SYNCED_ACCOUNT_TYPES).
    sync_enabled = Column(Boolean, nullable=False, server_default=false())
    last_synced_at = Column(DateTime, nullable=True)
    # Set when SnapTrade stops reporting this account (the user disconnected
    # or reconnected their brokerage, which gives accounts new ids). Trades
    # synced from it can then be taken over by the same account's new id
    # instead of being imported twice - see snaptrade_sync._find_match.
    disconnected_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "external_account_id", name="uq_brokerage_accounts_user_account"),)


class SnapTradeUser(Base):
    __tablename__ = "snaptrade_users"

    # With commercial (developer) SnapTrade keys, every InnerStock user gets
    # their own SnapTrade user, created the first time they press "Connect".
    # Not used with a personal key (that key IS one person's SnapTrade user).
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    # The id we registered with SnapTrade - random, never the email (SnapTrade
    # requires it to be immutable, and emails can change).
    snaptrade_user_id = Column(String, unique=True, nullable=False)
    # SnapTrade's per-user secret, encrypted with FIELD_ENCRYPTION_KEY
    # (secret_box.py) - never stored in plain text.
    user_secret_encrypted = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
