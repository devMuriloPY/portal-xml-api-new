from sqlalchemy import Column, String, Integer, Date, TIMESTAMP, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import relationship
from datetime import datetime
from zoneinfo import ZoneInfo
from app.db.database import Base

def agora_brasil():
    """Retorna datetime atual no fuso horário de Brasília"""
    return datetime.now(ZoneInfo("America/Sao_Paulo"))

class BatchRequest(Base):
    __tablename__ = "batch_requests"

    id = Column(String(255), primary_key=True, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending", 
                   index=True, 
                   server_default="pending")
    total_requests = Column(Integer, nullable=False)
    completed_requests = Column(Integer, default=0)
    failed_requests = Column(Integer, default=0)
    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date, nullable=False)
    created_at = Column(TIMESTAMP, default=agora_brasil)
    updated_at = Column(TIMESTAMP, default=agora_brasil, onupdate=agora_brasil)
    completed_at = Column(TIMESTAMP, nullable=True)

    # Relacionamento com os itens do lote
    items = relationship("BatchRequestItem", back_populates="batch", cascade="all, delete-orphan")

    # Constraint para validar status
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'error')",
            name="check_batch_status"
        ),
    )

class BatchRequestItem(Base):
    __tablename__ = "batch_request_items"

    id = Column(String(255), primary_key=True, index=True)
    batch_id = Column(String(255), ForeignKey("batch_requests.id", ondelete="CASCADE"), 
                     nullable=False, index=True)
    client_id = Column(String(255), nullable=False)
    client_name = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="pending", 
                   index=True, 
                   server_default="pending")
    xml_url = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    created_at = Column(TIMESTAMP, default=agora_brasil)
    updated_at = Column(TIMESTAMP, default=agora_brasil, onupdate=agora_brasil)
    completed_at = Column(TIMESTAMP, nullable=True)

    # Relacionamento com o lote
    batch = relationship("BatchRequest", back_populates="items")

    # Constraint para validar status
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'error')",
            name="check_item_status"
        ),
    )
