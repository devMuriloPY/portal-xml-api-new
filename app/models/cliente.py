from sqlalchemy import Column, Integer, String, ForeignKey
from app.db.database import Base

class Cliente(Base):
    __tablename__ = "clientes"

    id_cliente = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100))
    cnpj = Column(String(18), unique=True, index=True)  # 🔍 CNPJ Mantém a Máscara (único no banco)
    email = Column(String(100))  # Sem constraint unique no banco
    telefone = Column(String(15))
    id_contador = Column(Integer, ForeignKey("contadores.id_contador"), nullable=False)
