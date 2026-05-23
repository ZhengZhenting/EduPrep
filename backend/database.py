from sqlalchemy import create_engine # ORM framework for database interactions
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()
POSTGRESQL_PASSWORD = os.getenv("POSTGRESQL_PASSWORD") 

DATABASE_URL = f"postgresql://postgres:{POSTGRESQL_PASSWORD}@localhost:5432/eduprep"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) 

Base = declarative_base() # ORM base class

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()