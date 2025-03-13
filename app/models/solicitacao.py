from sqlalchemy import Column, Integer, Date, String, TIMESTAMP, ForeignKey
from app.db.database import Base

class Solicitacao(Base):
    __tablename__ = "solicitacoes"

    id_solicitacao = Column(Integer, primary_key=True, index=True)
    id_cliente = Column(Integer, ForeignKey("clientes.id_cliente"))
    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date, nullable=False)
    status = Column(String(20), default="pendente")
    data_solicitacao = Column(TIMESTAMP)
