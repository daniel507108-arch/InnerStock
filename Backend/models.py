from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

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
    created_at = Column(DateTime, server_default=func.now())


class PriceCache(Base):
    __tablename__ = "price_cache"

    ticker = Column(String, primary_key=True)
    current_price = Column(Numeric, nullable=False)
    market_cap = Column(Numeric, nullable=True)
    pe_ratio = Column(Numeric, nullable=True)
    sector = Column(String, nullable=True)
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())