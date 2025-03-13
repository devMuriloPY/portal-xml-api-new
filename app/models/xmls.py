from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from app.db.database import Base

class XML(Base):
    __tablename__ = "xmls"

    id_xml = Column(Integer, primary_key=True, index=True)
    id_cliente = Column(Integer, ForeignKey("clientes.id_cliente"))
    nome_arquivo = Column(String)
    url_arquivo = Column(String)
    data_envio = Column(DateTime)
    expiracao = Column(DateTime)
    id_solicitacao = Column(Integer, ForeignKey("solicitacoes.id_solicitacao"), nullable=True)
