from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import JWTError, jwt
import os

from app.db.database import SessionLocal
from app.models.contador import Contador
from app.models.cliente import Cliente
from app.utils.security import gerar_hash_senha, verificar_senha

# 🔐 Carregar SECRET_KEY do ambiente
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

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
