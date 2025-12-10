from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, BigInteger
from app.db.database import Base

class XML(Base):
    __tablename__ = "xmls"

    id_xml = Column(Integer, primary_key=True, index=True)
    id_cliente = Column(Integer, ForeignKey("clientes.id_cliente"), nullable=False)
    nome_arquivo = Column(String(100))
    url_arquivo = Column(String(1024))
    data_envio = Column(DateTime)
    expiracao = Column(DateTime)
    id_solicitacao = Column(Integer, ForeignKey("solicitacoes.id_solicitacao"), nullable=True)
    valor_nfe_autorizadas = Column(Numeric(13, 4))
    valor_nfe_canceladas = Column(Numeric(13, 4))
    valor_nfc_autorizadas = Column(Numeric(13, 4))
    valor_nfc_canceladas = Column(Numeric(13, 4))
    quantidade_nfe_autorizadas = Column(BigInteger)
    quantidade_nfe_canceladas = Column(BigInteger)
    quantidade_nfc_autorizadas = Column(BigInteger)
    quantidade_nfc_canceladas = Column(BigInteger)
