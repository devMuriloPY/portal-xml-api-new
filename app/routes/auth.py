from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from jose import JWTError, jwt
import os
import secrets
import hashlib
from typing import Optional

from app.db.database import get_db
from app.models.contador import Contador
from app.models.cliente import Cliente
from app.models.solicitacao import Solicitacao
from app.models.otp import OTP
from app.models.audit import AuditLog
from app.utils.security import gerar_hash_senha, verificar_senha
from app.utils.email_utils import enviar_email, renderizar_template_email
from app.utils.cnpj_mask import formatar_cnpj
from app.routes.websocket import conexoes_ativas

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
OTP_EXPIRE_MINUTES = 15
RESET_TOKEN_EXPIRE_MINUTES = 10
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://www.portalxml.wmsistemas.inf.br/")

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def agora_brasil():
    # Retorna um datetime sem fuso horário (offset-naive)
    return datetime.now().replace(tzinfo=None)

def converter_data_segura(data_str: str) -> datetime.date:
    return datetime.strptime(data_str, "%Y-%m-%d").date()

def gerar_otp() -> str:
    """Gera um código OTP de 4 dígitos"""
    return f"{secrets.randbelow(10000):04d}"

def hash_otp(otp: str) -> str:
    """Gera hash do OTP para armazenamento seguro"""
    return hashlib.sha256(otp.encode()).hexdigest()

def verificar_otp(otp: str, otp_hash: str) -> bool:
    """Verifica se o OTP está correto usando comparação em tempo constante"""
    return secrets.compare_digest(hash_otp(otp), otp_hash)

async def log_audit(db: AsyncSession, user_id: Optional[int], identifier: str, action: str, 
                   ip_address: Optional[str], result: str, details: Optional[str] = None):
    """Registra ação de auditoria"""
    audit_log = AuditLog(
        user_id=user_id,
        identifier=identifier,
        action=action,
        ip_address=ip_address,
        result=result,
        details=details
    )
    db.add(audit_log)
    await db.commit()

async def encontrar_contador_por_identificador(db: AsyncSession, identifier: str) -> Optional[Contador]:
    """Encontra contador por email ou CNPJ"""
    identifier = identifier.strip()
    
    if "@" in identifier:
        # É um email
        result = await db.execute(select(Contador).where(Contador.email == identifier))
    else:
        # É um CNPJ
        cnpj_formatado = formatar_cnpj(identifier)
        result = await db.execute(select(Contador).where(Contador.cnpj == cnpj_formatado))
    
    return result.scalars().first()

class PrimeiroAcesso(BaseModel):
    cnpj: str
    senha: str
    senha_confirmacao: str

class LoginSchema(BaseModel):
    cnpj: str
    senha: str

class OTPRequest(BaseModel):
    identifier: str

class OTPVerify(BaseModel):
    identifier: str
    code: str

class PasswordReset(BaseModel):
    new_password: str

class CriarSolicitacao(BaseModel):
    id_cliente: int
    data_inicio: str
    data_fim: str

class AtualizarStatusSolicitacao(BaseModel):
    id_solicitacao: int
    novo_status: str

class ExclusaoSolicitacao(BaseModel):
    id_solicitacao: int

# 📌 Primeiro Acesso
@router.post("/primeiro-acesso")
async def primeiro_acesso(dados: PrimeiroAcesso, db: AsyncSession = Depends(get_db)):
    cnpj_formatado = formatar_cnpj(dados.cnpj)
    result = await db.execute(select(Contador).where(Contador.cnpj == cnpj_formatado))
    contador = result.scalars().first()

    if not contador:
        raise HTTPException(status_code=404, detail="CNPJ não encontrado")

    if contador.senha_hash:
        raise HTTPException(status_code=400, detail="Usuário já possui senha cadastrada")

    if dados.senha != dados.senha_confirmacao:
        raise HTTPException(status_code=400, detail="As senhas não coincidem")

    contador.senha_hash = gerar_hash_senha(dados.senha)
    await db.commit()

    return JSONResponse(content={"message": "Senha cadastrada com sucesso!"}, status_code=201)

# 🔐 Login
@router.post("/login")
async def login(dados: LoginSchema, db: AsyncSession = Depends(get_db)):
    cnpj_formatado = formatar_cnpj(dados.cnpj)
    result = await db.execute(select(Contador).where(Contador.cnpj == cnpj_formatado))
    contador = result.scalars().first()

    if not contador or not contador.senha_hash:
        raise HTTPException(status_code=404, detail="Usuário não encontrado ou sem senha cadastrada")

    if not verificar_senha(dados.senha, contador.senha_hash):
        raise HTTPException(status_code=401, detail="Senha incorreta")

    token = jwt.encode(
        {"sub": contador.cnpj, "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)},
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return {"access_token": token, "token_type": "bearer"}

# 🔐 Autenticação
async def obter_contador_logado(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        cnpj = payload.get("sub")
        if not cnpj:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
        result = await db.execute(select(Contador).where(Contador.cnpj == cnpj))
        contador = result.scalars().first()
        if not contador:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado")
        return contador
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado")

# 📌 Dados do contador
@router.get("/me")
async def obter_dados_contador(contador: Contador = Depends(obter_contador_logado), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Cliente).where(Cliente.id_contador == contador.id_contador))
    total_clientes = len(result.scalars().all())

    return {
        "id_contador": contador.id_contador,
        "nome": contador.nome,
        "email": contador.email,
        "cnpj": contador.cnpj,
        "total_clientes": total_clientes
    }

# 📌 Listar clientes
@router.get("/clientes")
async def listar_clientes(contador: Contador = Depends(obter_contador_logado), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Cliente).where(Cliente.id_contador == contador.id_contador))
    clientes = result.scalars().all()

    if not clientes:
        return {"mensagem": "Nenhum cliente encontrado"}

    return [
        {
            "id_cliente": cliente.id_cliente,
            "nome": cliente.nome,
            "cnpj": formatar_cnpj(cliente.cnpj),
            "email": cliente.email,
            "telefone": cliente.telefone
        }
        for cliente in clientes
    ]

# 📌 Obter cliente por ID
@router.get("/clientes/{id_cliente}")
async def obter_cliente(id_cliente: int, contador: Contador = Depends(obter_contador_logado), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Cliente).where(
            Cliente.id_cliente == id_cliente,
            Cliente.id_contador == contador.id_contador
        )
    )
    cliente = result.scalars().first()

    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    return {
        "id_cliente": cliente.id_cliente,
        "nome": cliente.nome,
        "cnpj": formatar_cnpj(cliente.cnpj),
        "email": cliente.email,
        "telefone": cliente.telefone
    }

# 📌 Solicitar OTP para redefinição de senha
@router.post("/password/otp/request")
async def solicitar_otp(dados: OTPRequest, request: Request, db: AsyncSession = Depends(get_db)):
    identifier = dados.identifier.strip()
    ip_address = request.client.host if request.client else None
    
    # Busca silenciosa - não revela se a conta existe
    contador = await encontrar_contador_por_identificador(db, identifier)
    
    if contador:
        # Gera OTP
        otp_code = gerar_otp()
        otp_hash = hash_otp(otp_code)
        
        # Expiração em 15 minutos
        expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRE_MINUTES)
        
        # Cria registro OTP
        otp_record = OTP(
            identifier=identifier,
            otp_hash=otp_hash,
            expires_at=expires_at,
            max_attempts=5
        )
        
        db.add(otp_record)
        await db.commit()
        
        # Envia email com OTP
        corpo_html = renderizar_template_email("otp_template.html", {
            "nome": contador.nome,
            "codigo": otp_code
        })
        
        enviar_email(
            destinatario=contador.email,
            assunto="Código de Verificação - Redefinição de Senha",
            corpo=corpo_html
        )
        
        # Log de auditoria
        await log_audit(db, contador.id_contador, identifier, "otp_request", ip_address, "success")
    
    # Sempre retorna a mesma mensagem, independente de existir ou não
    return {"message": "Se existir uma conta, enviamos um código para o e-mail cadastrado."}

# 📌 Verificar OTP
@router.post("/password/otp/verify")
async def verificar_otp_endpoint(dados: OTPVerify, request: Request, db: AsyncSession = Depends(get_db)):
    identifier = dados.identifier.strip()
    code = dados.code.strip()
    ip_address = request.client.host if request.client else None
    
    # Busca OTP válido
    result = await db.execute(
        select(OTP).where(
            OTP.identifier == identifier,
            OTP.used == False,
            OTP.expires_at > datetime.utcnow()
        ).order_by(OTP.created_at.desc())
    )
    otp_record = result.scalars().first()
    
    if not otp_record:
        await log_audit(db, None, identifier, "otp_verify", ip_address, "error", "OTP não encontrado ou expirado")
        return {"status": "error"}
    
    # Verifica se excedeu tentativas
    if otp_record.attempts >= otp_record.max_attempts:
        otp_record.used = True
        await db.commit()
        await log_audit(db, None, identifier, "otp_verify", ip_address, "error", "Máximo de tentativas excedido")
        return {"status": "error"}
    
    # Incrementa tentativas
    otp_record.attempts += 1
    
    # Verifica código
    if verificar_otp(code, otp_record.otp_hash):
        # Sucesso - gera reset token
        contador = await encontrar_contador_por_identificador(db, identifier)
        if not contador:
            await db.commit()
            await log_audit(db, None, identifier, "otp_verify", ip_address, "error", "Usuário não encontrado")
            return {"status": "error"}
        
        # Marca OTP como usado
        otp_record.used = True
        
        # Gera reset token (10 minutos, single-use)
        expires_at = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
        reset_token = jwt.encode({
            "sub": contador.email,
            "exp": expires_at,
            "type": "password_reset",
            "otp_id": otp_record.id_otp
        }, SECRET_KEY, algorithm=ALGORITHM)
        
        await db.commit()
        await log_audit(db, contador.id_contador, identifier, "otp_verify", ip_address, "success")
        
        return {"status": "ok", "reset_token": reset_token}
    else:
        # Código incorreto
        await db.commit()
        await log_audit(db, None, identifier, "otp_verify", ip_address, "error", f"Tentativa {otp_record.attempts}")
        return {"status": "error"}

# 📌 Redefinir senha com reset token
@router.post("/password/reset")
async def redefinir_senha(dados: PasswordReset, request: Request, db: AsyncSession = Depends(get_db)):
    # Verifica token de autorização
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token de autorização necessário")
    
    reset_token = auth_header.split(" ")[1]
    ip_address = request.client.host if request.client else None
    
    try:
        payload = jwt.decode(reset_token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        token_type = payload.get("type")
        otp_id = payload.get("otp_id")
        
        if token_type != "password_reset":
            raise HTTPException(status_code=400, detail="Token inválido")
            
    except JWTError:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")
    
    # Busca contador
    result = await db.execute(select(Contador).where(Contador.email == email))
    contador = result.scalars().first()
    
    if not contador:
        await log_audit(db, None, email, "password_reset", ip_address, "error", "Usuário não encontrado")
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    # Verifica se OTP foi usado (single-use token)
    if otp_id:
        otp_result = await db.execute(select(OTP).where(OTP.id_otp == otp_id))
        otp_record = otp_result.scalars().first()
        if otp_record and not otp_record.used:
            otp_record.used = True  # Marca como usado para invalidar token
    
    # Atualiza senha
    contador.senha_hash = gerar_hash_senha(dados.new_password)
    await db.commit()
    
    # Log de auditoria
    await log_audit(db, contador.id_contador, email, "password_reset", ip_address, "success")
    
    return {"message": "Senha atualizada."}

# 📌 Atualizar status da solicitação (chamado pelo desktop)
@router.put("/solicitacoes/status")
async def atualizar_status_solicitacao(dados: AtualizarStatusSolicitacao, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Solicitacao).where(Solicitacao.id_solicitacao == dados.id_solicitacao))
    solicitacao = result.scalars().first()
    
    if not solicitacao:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    
    solicitacao.status = dados.novo_status
    await db.commit()
    
    return {"mensagem": f"Status atualizado para {dados.novo_status}"}

# 📌 Criar solicitação
@router.post("/solicitacoes")
async def criar_solicitacao(dados: CriarSolicitacao, db: AsyncSession = Depends(get_db)):
    try:
        # Converte as datas para datetime.date (já são offset-naive)
        data_inicio_api = converter_data_segura(dados.data_inicio) + timedelta(days=1)
        data_fim_api = converter_data_segura(dados.data_fim) + timedelta(days=1)
        
        data_inicio = converter_data_segura(dados.data_inicio)
        data_fim = converter_data_segura(dados.data_fim)
        # Cria a solicitação com data_solicitacao offset-naive
        nova = Solicitacao(
            id_cliente=dados.id_cliente,
            data_inicio=data_inicio_api,
            data_fim=data_fim_api,
            status="pendente",
            data_solicitacao=agora_brasil()  # Agora retorna um datetime sem fuso horário
        )

        db.add(nova)
        await db.commit()
        await db.refresh(nova)

        # Notifica via WebSocket (se necessário)
        websocket = conexoes_ativas.get(dados.id_cliente)
        if websocket:
            await websocket.send_json({
                "id_cliente": dados.id_cliente,
                "data_inicio": str(data_inicio),
                "data_fim": str(data_fim),
                "id_solicitacao": nova.id_solicitacao
            })

        return {
            "status": "Solicitação registrada",
            "id_solicitacao": nova.id_solicitacao
        }
    except SQLAlchemyError as e:
        await db.rollback()
        print(f"Erro ao criar solicitação: {e}")
        raise HTTPException(status_code=500, detail="Erro ao criar solicitação")

# 📌 Listar solicitações
@router.get("/solicitacoes/{id_cliente}")
async def listar_solicitacoes(id_cliente: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Solicitacao).where(Solicitacao.id_cliente == id_cliente).order_by(Solicitacao.data_solicitacao.desc())
    )
    solicitacoes = result.scalars().all()
    agora = datetime.utcnow()
    resposta = []

    for s in solicitacoes:
        xml = await db.execute(
            text("""
                SELECT 
                    url_arquivo,
                    expiracao,
                    valor_nfe_autorizadas,
                    valor_nfe_canceladas,
                    valor_nfc_autorizadas,
                    valor_nfc_canceladas,
                    quantidade_nfe_autorizadas,
                    quantidade_nfe_canceladas,
                    quantidade_nfc_autorizadas,
                    quantidade_nfc_canceladas
                FROM xmls
                WHERE id_solicitacao = :id
            """),
            {"id": s.id_solicitacao}
        )
        xml_data = xml.fetchone()

        # Converter para fuso horário de Brasília
        if s.data_solicitacao:
            # Se o datetime não tem timezone, assumir que é UTC e converter para Brasília
            if s.data_solicitacao.tzinfo is None:
                # Adicionar timezone UTC e converter para Brasília
                data_utc = s.data_solicitacao.replace(tzinfo=ZoneInfo("UTC"))
                data_brasilia = data_utc.astimezone(ZoneInfo("America/Sao_Paulo"))
                data_solicitacao = data_brasilia.isoformat()
            else:
                # Se já tem timezone, converter para Brasília
                data_brasilia = s.data_solicitacao.astimezone(ZoneInfo("America/Sao_Paulo"))
                data_solicitacao = data_brasilia.isoformat()
        else:
            data_solicitacao = None

        # Verificar se xml_data existe antes de acessar os índices
        if xml_data and xml_data[1] > agora:
            status = "concluido"
            xml_url = xml_data[0]
            valor_nfe_autorizadas = xml_data[2]
            valor_nfe_canceladas = xml_data[3]
            valor_nfc_autorizadas = xml_data[4]
            valor_nfc_canceladas = xml_data[5]
            quantidade_nfe_autorizadas = xml_data[6]
            quantidade_nfe_canceladas = xml_data[7]
            quantidade_nfc_autorizadas = xml_data[8]
            quantidade_nfc_canceladas = xml_data[9]
        else:
            status = s.status
            xml_url = None
            valor_nfe_autorizadas = None
            valor_nfe_canceladas = None
            valor_nfc_autorizadas = None
            valor_nfc_canceladas = None
            quantidade_nfe_autorizadas = None
            quantidade_nfe_canceladas = None
            quantidade_nfc_autorizadas = None
            quantidade_nfc_canceladas = None

        resposta.append({
            "id_solicitacao": s.id_solicitacao,
            "data_inicio": s.data_inicio,
            "data_fim": s.data_fim,
            "status": status,
            "xml_url": xml_url,
            "data_solicitacao": data_solicitacao,
            "valor_nfe_autorizadas": valor_nfe_autorizadas,
            "valor_nfe_canceladas": valor_nfe_canceladas,
            "valor_nfc_autorizadas": valor_nfc_autorizadas,
            "valor_nfc_canceladas": valor_nfc_canceladas,
            "quantidade_nfe_autorizadas": quantidade_nfe_autorizadas,
            "quantidade_nfe_canceladas": quantidade_nfe_canceladas,
            "quantidade_nfc_autorizadas": quantidade_nfc_autorizadas,
            "quantidade_nfc_canceladas": quantidade_nfc_canceladas
        })

    return resposta

# 📌 Excluir solicitação
@router.delete("/solicitacoes")
async def deletar_solicitacao(payload: ExclusaoSolicitacao, db: AsyncSession = Depends(get_db)):
    id_solicitacao = payload.id_solicitacao

    result = await db.execute(select(Solicitacao).where(Solicitacao.id_solicitacao == id_solicitacao))
    solicitacao = result.scalars().first()

    if not solicitacao:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")

    await db.execute(text("DELETE FROM xmls WHERE id_solicitacao = :id"), {"id": id_solicitacao})
    await db.delete(solicitacao)
    await db.commit()

    return {"status": "Solicitação deletada com sucesso", "id_solicitacao": id_solicitacao}


