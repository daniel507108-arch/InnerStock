from database import engine, SessionLocal, Base
from models import User, Trade, PriceCache, SentimentCache

Base.metadata.create_all(bind=engine)

print("Database ready: tables created.")