from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from urllib.parse import quote_plus  # ✅ usado para codificar parâmetros
import os

POSTGRES_CONFIG = {
    'host': 'tramway.proxy.rlwy.net',
    'port': 36869,
    'dbname': 'railway',
    'user': 'postgres',
    'password': 'vanYmOoqXBjWNJkJszijhShyUdQJMWVx'
}

# ✅ Codifica o parâmetro --timezone=America/Sao_Paulo
timezone_param = quote_plus("--timezone=America/Sao_Paulo")

# ✅ Inclui o parâmetro options=... na URL
DATABASE_URL = f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@" \
               f"{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['dbname']}?options={timezone_param}"

# ✅ echo=True apenas se quiser ver as queries SQL no terminal
engine = create_engine(DATABASE_URL, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
