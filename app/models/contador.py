from sqlalchemy import Column, Integer, String
from app.db.database import Base

class Contador(Base):
    __tablename__ = "contadores"

    id_contador = Column(Integer, primary_key=True, index=True)
    nome = Column(String)
    cnpj = Column(String, unique=True, index=True)  # Já vem com máscara no banco
    email = Column(String, unique=True, index=True)
    senha_hash = Column(String, nullable=True)  # Pode estar vazio para novos acessos
