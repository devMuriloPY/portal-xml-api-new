from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from datetime import datetime
from zoneinfo import ZoneInfo
from app.db.database import Base

def agora_brasil():
    """Retorna datetime atual no fuso horário de Brasília (sem timezone)"""
    return datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None)

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id_audit = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)  # ID do usuário (pode ser null se não encontrado)
    identifier = Column(String, nullable=True)  # email ou CNPJ usado
    action = Column(String, nullable=False)  # Tipo de ação (otp_request, otp_verify, password_reset)
    ip_address = Column(String, nullable=True)  # IP do usuário
    result = Column(String, nullable=False)  # success, error, not_found, etc.
    details = Column(Text, nullable=True)  # Detalhes adicionais
    created_at = Column(DateTime, default=agora_brasil)  # Data da ação
