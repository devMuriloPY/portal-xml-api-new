from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from app.db.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id_audit = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)  # ID do usuário (pode ser null se não encontrado)
    identifier = Column(String, nullable=True)  # email ou CNPJ usado
    action = Column(String, nullable=False)  # Tipo de ação (otp_request, otp_verify, password_reset)
    ip_address = Column(String, nullable=True)  # IP do usuário
    result = Column(String, nullable=False)  # success, error, not_found, etc.
    details = Column(Text, nullable=True)  # Detalhes adicionais
    created_at = Column(DateTime, default=func.now())  # Data da ação
