from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import JSONResponse
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
from app.utils.email_utils import enviar_email, renderizar_template_email
from app.utils.cnpj_mask import formatar_cnpj  # Importa a função

# 🔐 Carregar SECRET_KEY do ambiente
SECRET_KEY = os.getenv("SECRET_KEY")
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



@router.post("/primeiro-acesso")
def primeiro_acesso(dados: PrimeiroAcesso, db: Session = Depends(get_db)):
    cnpj_formatado = formatar_cnpj(dados.cnpj)  # 🔹 Aplica a formatação antes de buscar no banco
    contador = db.query(Contador).filter(Contador.cnpj == cnpj_formatado).first()

    if not contador:
        raise HTTPException(status_code=404, detail="CNPJ não encontrado")

    if contador.senha_hash:
        raise HTTPException(status_code=400, detail="Usuário já possui senha cadastrada")

    if dados.senha != dados.senha_confirmacao:
        raise HTTPException(status_code=400, detail="As senhas não coincidem")

    contador.senha_hash = gerar_hash_senha(dados.senha)
    db.commit()

    return JSONResponse(content={"message": "Senha cadastrada com sucesso!"}, status_code=201)

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
        print(f"🔍 Token recebido: {token}")  # ✅ Verifica se o token está chegando

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print(f"🔍 Payload decodificado: {payload}")  # ✅ Mostra os dados do token

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
            "cnpj": formatar_cnpj(cliente.cnpj),  # 🔹 Aplica a formatação antes de retornar
            "email": cliente.email,
            "telefone": cliente.telefone
        }
        for cliente in clientes
    ]


class SolicitarRedefinicao(BaseModel):
    email: EmailStr

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")  # Define o link do frontend

# Endpoint para solicitar redefinição de senha
@router.post("/solicitar-redefinicao")
def solicitar_redefinicao(dados: SolicitarRedefinicao, db: Session = Depends(get_db)):
    contador = db.query(Contador).filter(Contador.email == dados.email).first()

    if not contador:
        raise HTTPException(status_code=404, detail="E-mail não encontrado")

    expiracao = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    token_redefinicao = jwt.encode({"sub": contador.email, "exp": expiracao}, SECRET_KEY, algorithm=ALGORITHM)

    link_redefinicao = f"{FRONTEND_URL}/redefinir-senha?token={token_redefinicao}"

    # ✅ Renderiza o template com o nome e link
    corpo_html = renderizar_template_email("redefinir_senha.html", {
        "nome": contador.nome,
        "link": link_redefinicao
    })

    enviar_email(
        destinatario=contador.email,
        assunto="Redefinição de Senha",
        corpo=corpo_html
    )

    return Response(content="E-mail de redefinição enviado com sucesso", status_code=200)
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

@router.get("/me")
def obter_dados_contador(
    contador: Contador = Depends(obter_contador_logado),
    db: Session = Depends(get_db)
):
    total_clientes = db.query(Cliente).filter(Cliente.id_contador == contador.id_contador).count()

    return {
        "id_contador": contador.id_contador,
        "nome": contador.nome,
        "email": contador.email,
        "cnpj": contador.cnpj,
        "total_clientes": total_clientes  # 👈 agora vem junto
    }
