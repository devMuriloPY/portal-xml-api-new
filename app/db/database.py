from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

POSTGRES_CONFIG = {
    'host': 'tramway.proxy.rlwy.net',
    'port': 36869,
    'dbname': 'railway',
    'user': 'postgres',
    'password': 'vanYmOoqXBjWNJkJszijhShyUdQJMWVx'
}

DATABASE_URL = f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@" \
               f"{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['dbname']}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
