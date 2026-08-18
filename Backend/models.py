from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
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
    trading_style = Column(String, nullable=False)       # e.g. "buy_and_hold", "active", "swing"
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
    thesis_text = Column(Text, nullable=False)
    conviction_score = Column(Integer, nullable=False)   # 1-5
    review_date = Column(Date, nullable=False)
    outcome_tag = Column(String, nullable=True)       # stays empty until resurfaced & graded
    review_notes = Column(Text, nullable=True)         # NEW — optional freeform reflection, added at grading time
    created_at = Column(DateTime, server_default=func.now())


class PriceCache(Base):
    __tablename__ = "price_cache"

    ticker = Column(String, primary_key=True)
    current_price = Column(Numeric, nullable=False)
    previous_close = Column(Numeric, nullable=True)
    market_cap = Column(Numeric, nullable=True)
    pe_ratio = Column(Numeric, nullable=True)
    sector = Column(String, nullable=True)
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String, nullable=False)     # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())