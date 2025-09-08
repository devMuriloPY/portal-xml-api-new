from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Configurações do banco de dados a partir das variáveis de ambiente
POSTGRES_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'dbname': os.getenv('DB_NAME', 'postgres'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '')
}

DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}" \
               f"@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['dbname']}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,          # opcional: aumenta o limite padrão do pool
    max_overflow=20,       # opcional: permite mais conexões temporárias
    pool_timeout=30
)

async_session = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

# Dependência do FastAPI
async def get_db():
    async with async_session() as session:
        yield session
