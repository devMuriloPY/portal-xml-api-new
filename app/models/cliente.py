from sqlalchemy import Column, Integer, String, ForeignKey
from app.db.database import Base

class Cliente(Base):
    __tablename__ = "clientes"

    id_cliente = Column(Integer, primary_key=True, index=True)
    nome = Column(String)
    cnpj = Column(String, unique=True, index=True)  # 🔍 CNPJ Mantém a Máscara
    email = Column(String, unique=True)
    telefone = Column(String)
    celular = Column(String)
    id_contador = Column(Integer, ForeignKey("contadores.id_contador"))
