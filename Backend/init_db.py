from database import engine, SessionLocal, Base
from models import User, Trade, PriceCache

Base.metadata.create_all(bind=engine)

db = SessionLocal()
if not db.query(User).first():
    db.add(User(id=1, name="Daniel"))
    db.commit()
db.close()

print("Database ready: tables created, default user seeded.")