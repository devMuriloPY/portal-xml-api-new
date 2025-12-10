from sqlalchemy import Column, Integer, String
from app.db.database import Base

class Contador(Base):
    __tablename__ = "contadores"

    id_contador = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100))
    cnpj = Column(String(18), unique=True, index=True)  # Já vem com máscara no banco (único)
    email = Column(String(100))  # Sem constraint unique no banco
    senha_hash = Column(String(255), nullable=True)  # Pode estar vazio para novos acessos
