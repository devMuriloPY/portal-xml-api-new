from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from jose import JWTError, jwt
import os

from app.db.database import SessionLocal
from app.models.contador import Contador
from app.models.cliente import Cliente
from app.utils.security import gerar_hash_senha, verificar_senha
from app.utils.email_utils import enviar_email 
# 🔐 Carregar SECRET_KEY do ambiente

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("🚨 ERRO: SECRET_KEY não encontrada nas variáveis de ambiente.")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
RESET_TOKEN_EXPIRE_MINUTES = 30

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# 📌 Função para obter a sessão do banco
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 📌 Modelos de Entrada
class PrimeiroAcesso(BaseModel):
    cnpj: str
    senha: str
    senha_confirmacao: str

class LoginSchema(BaseModel):
    cnpj: str
    senha: str

# 📌 Endpoint para Primeiro Acesso (Criação de Senha)
@router.post("/primeiro-acesso")
def primeiro_acesso(dados: PrimeiroAcesso, db: Session = Depends(get_db)):
    # 🔍 Buscar o CNPJ exatamente como está no banco (com máscara)
    contador = db.query(Contador).filter(Contador.cnpj == dados.cnpj).first()

    if not contador:
        raise HTTPException(status_code=404, detail="CNPJ não encontrado")

    if contador.senha_hash:
        raise HTTPException(status_code=400, detail="Usuário já possui senha cadastrada")

    if dados.senha != dados.senha_confirmacao:
        raise HTTPException(status_code=400, detail="As senhas não coincidem")

    contador.senha_hash = gerar_hash_senha(dados.senha)
    db.commit()

    return {"status": "Senha cadastrada com sucesso!"}

# 📌 Endpoint para Login
@router.post("/login")
def login(dados: LoginSchema, db: Session = Depends(get_db)):
    # 🔍 Buscar o CNPJ no banco exatamente como está (com máscara)
    contador = db.query(Contador).filter(Contador.cnpj == dados.cnpj).first()

    if not contador or not contador.senha_hash:
        raise HTTPException(status_code=404, detail="Usuário não encontrado ou sem senha cadastrada")

    if not verificar_senha(dados.senha, contador.senha_hash):
        raise HTTPException(status_code=401, detail="Senha incorreta")

    # 🔐 Gerar Token JWT
    token = jwt.encode(
        {"sub": contador.cnpj, "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)},
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return {"access_token": token, "token_type": "bearer"}

# 📌 Função para Validar Token JWT
def obter_contador_logado(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        cnpj = payload.get("sub")

        if cnpj is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

        contador = db.query(Contador).filter(Contador.cnpj == cnpj).first()
        if contador is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado")

        return contador

    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado")

# 📌 Endpoint para Retornar os Clientes do Contador Autenticado
@router.get("/clientes")
def listar_clientes(contador: Contador = Depends(obter_contador_logado), db: Session = Depends(get_db)):
    clientes = db.query(Cliente).filter(Cliente.id_contador == contador.id_contador).all()

    if not clientes:
        return {"mensagem": "Nenhum cliente encontrado"}

    return [
        {
            "id_cliente": cliente.id_cliente,
            "nome": cliente.nome,
            "cnpj": cliente.cnpj,  # 🔍 Mantendo a máscara no retorno
            "email": cliente.email,
            "telefone": cliente.telefone
        }
        for cliente in clientes
    ]

class SolicitarRedefinicao(BaseModel):
    email: EmailStr

# Endpoint para solicitar redefinição de senha
@router.post("/solicitar-redefinicao")
def solicitar_redefinicao(dados: SolicitarRedefinicao, db: Session = Depends(get_db)):
    contador = db.query(Contador).filter(Contador.email == dados.email).first()

    if not contador:
        raise HTTPException(status_code=404, detail="E-mail não encontrado")

    # Gerar um token de redefinição de senha (válido por 30 minutos)
    expiracao = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    token_redefinicao = jwt.encode({"sub": contador.email, "exp": expiracao}, SECRET_KEY, algorithm=ALGORITHM)

    # Criar link de redefinição de senha
    url_base = os.getenv("FRONTEND_URL", "http://localhost:3000")
    link_redefinicao = f"{url_base}/redefinir-senha?token={token_redefinicao}"

    # Enviar o e-mail com o link de redefinição
    enviar_email(
        destinatario=contador.email,
        assunto="Redefinição de Senha",
        corpo=f"""
        <p>Olá, {contador.nome},</p>
        <p>Recebemos uma solicitação para redefinir sua senha. Clique no link abaixo para definir uma nova senha:</p>
        <p><a href="{link_redefinicao}">Redefinir Senha</a></p>
        <p>Se você não solicitou essa alteração, ignore este e-mail.</p>
        """
    )

    return {"mensagem": "E-mail de redefinição enviado com sucesso"}


# Modelo de entrada para redefinir senha
class RedefinirSenha(BaseModel):
    token: str
    nova_senha: str
    confirmar_senha: str

# Endpoint para redefinir a senha
@router.post("/redefinir-senha")
def redefinir_senha(dados: RedefinirSenha, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(dados.token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
    except:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")

    contador = db.query(Contador).filter(Contador.email == email).first()

    if not contador:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if dados.nova_senha != dados.confirmar_senha:
        raise HTTPException(status_code=400, detail="As senhas não coincidem")

    # Atualizar a senha no banco
    contador.senha_hash = gerar_hash_senha(dados.nova_senha)
    db.commit()

    return {"mensagem": "Senha redefinida com sucesso"}
