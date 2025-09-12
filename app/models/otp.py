from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from app.db.database import Base

class OTP(Base):
    __tablename__ = "otps"

    id_otp = Column(Integer, primary_key=True, index=True)
    identifier = Column(String, index=True)  # email ou CNPJ
    otp_hash = Column(String)  # Hash do código OTP
    attempts = Column(Integer, default=0)  # Número de tentativas
    max_attempts = Column(Integer, default=5)  # Máximo de tentativas
    expires_at = Column(DateTime, nullable=False)  # Data de expiração
    used = Column(Boolean, default=False)  # Se foi usado
    created_at = Column(DateTime, default=func.now())  # Data de criação
