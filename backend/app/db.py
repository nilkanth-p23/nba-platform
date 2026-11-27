import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

database_url = os.getenv("COURTSIDE_DATABASE_URL") or os.environ["DATABASE_URL"]
for prefix in ("postgres://", "postgresql://"):
    if database_url.startswith(prefix):
        database_url = "postgresql+psycopg://" + database_url.removeprefix(prefix)
        break

engine = create_engine(database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
