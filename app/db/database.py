from sqlalchemy import create_engine, event
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

engine = create_engine(DATABASE_URL, echo=False)

# ✅ Executa SET TIME ZONE ao conectar
@event.listens_for(engine, "connect")
def set_timezone(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("SET TIME ZONE 'America/Sao_Paulo';")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
