from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from jose import JWTError, jwt
from sqlalchemy import text
from zoneinfo import ZoneInfo
import os

from app.db.database import SessionLocal
from app.models.contador import Contador
from app.models.cliente import Cliente
from app.models.solicitacao import Solicitacao
from app.utils.security import gerar_hash_senha, verificar_senha
from app.utils.email_utils import enviar_email, renderizar_template_email
from app.utils.cnpj_mask import formatar_cnpj
from app.routes.websocket import conexoes_ativas  # ajuste o caminho conforme seu projeto

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
RESET_TOKEN_EXPIRE_MINUTES = 30
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# 📌 Sessão do banco
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 📌 Modelos Pydantic
class PrimeiroAcesso(BaseModel):
    cnpj: str
    senha: str
    senha_confirmacao: str

class LoginSchema(BaseModel):
    cnpj: str
    senha: str

class SolicitarRedefinicao(BaseModel):
    identificador: str

class RedefinirSenha(BaseModel):
    token: str
    nova_senha: str
    confirmar_senha: str

class CriarSolicitacao(BaseModel):
    id_cliente: int
    data_inicio: str
    data_fim: str


# 📌 Primeiro Acesso
@router.post("/primeiro-acesso")
def primeiro_acesso(dados: PrimeiroAcesso, db: Session = Depends(get_db)):
    cnpj_formatado = formatar_cnpj(dados.cnpj)
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


# 📌 Login
@router.post("/login")
def login(dados: LoginSchema, db: Session = Depends(get_db)):
    contador = db.query(Contador).filter(Contador.cnpj == dados.cnpj).first()

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


# 📌 Autenticação
def obter_contador_logado(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        cnpj = payload.get("sub")
        if not cnpj:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
        contador = db.query(Contador).filter(Contador.cnpj == cnpj).first()
        if not contador:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado")
        return contador
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado")


# 📌 Retornar dados do contador
@router.get("/me")
def obter_dados_contador(contador: Contador = Depends(obter_contador_logado), db: Session = Depends(get_db)):
    total_clientes = db.query(Cliente).filter(Cliente.id_contador == contador.id_contador).count()

    return {
        "id_contador": contador.id_contador,
        "nome": contador.nome,
        "email": contador.email,
        "cnpj": contador.cnpj,
        "total_clientes": total_clientes
    }


# 📌 Listar clientes
@router.get("/clientes")
def listar_clientes(contador: Contador = Depends(obter_contador_logado), db: Session = Depends(get_db)):
    clientes = db.query(Cliente).filter(Cliente.id_contador == contador.id_contador).all()

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


# 📌 Solicitar redefinição
@router.post("/solicitar-redefinicao")
def solicitar_redefinicao(dados: SolicitarRedefinicao, db: Session = Depends(get_db)):
    identificador = dados.identificador.strip()

    if "@" in identificador:
        contador = db.query(Contador).filter(Contador.email == identificador).first()
    else:
        cnpj_formatado = formatar_cnpj(identificador)
        contador = db.query(Contador).filter(Contador.cnpj == cnpj_formatado).first()

    if not contador:
        raise HTTPException(status_code=404, detail="E-mail ou CNPJ não encontrado")

    expiracao = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    token_redefinicao = jwt.encode({"sub": contador.email, "exp": expiracao}, SECRET_KEY, algorithm=ALGORITHM)
    link_redefinicao = f"{FRONTEND_URL}/redefinir-senha?token={token_redefinicao}"

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


# 📌 Redefinir senha
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

    contador.senha_hash = gerar_hash_senha(dados.nova_senha)
    db.commit()

    return {"mensagem": "Senha redefinida com sucesso"}


@router.post("/solicitacoes")
async def criar_solicitacao(dados: CriarSolicitacao, db: Session = Depends(get_db)):
    # 🧠 Converte strings para `datetime.date`
    data_inicio = datetime.strptime(dados.data_inicio, "%Y-%m-%d").date()
    data_fim = datetime.strptime(dados.data_fim, "%Y-%m-%d").date()

    nova = Solicitacao(
        id_cliente=dados.id_cliente,
        data_inicio=data_inicio,
        data_fim=data_fim,
        status="pendente",
        data_solicitacao = datetime.now(ZoneInfo("America/Sao_Paulo"))
    )

    db.add(nova)
    db.commit()
    db.refresh(nova)

    # ✅ Enviar via WebSocket diretamente
    websocket = conexoes_ativas.get(dados.id_cliente)
    if websocket:
        await websocket.send_json({
            "id_cliente": dados.id_cliente,
            "data_inicio": dados.data_inicio,
            "data_fim": dados.data_fim,
            "id_solicitacao": nova.id_solicitacao
        })
    else:
        print(f"⚠️ Cliente {dados.id_cliente} não está conectado via WebSocket.")

    return {
        "status": "Solicitação registrada",
        "id_solicitacao": nova.id_solicitacao
    }

@router.get("/solicitacoes/{id_cliente}")
def listar_solicitacoes(id_cliente: int, db: Session = Depends(get_db)):
    solicitacoes = db.query(Solicitacao).filter(
        Solicitacao.id_cliente == id_cliente
    ).order_by(Solicitacao.data_solicitacao.desc()).all()

    agora = datetime.utcnow()
    resultado = []

    for s in solicitacoes:
        xml = db.execute(
            text("SELECT url_arquivo, expiracao FROM xmls WHERE id_solicitacao = :id"),
            {"id": s.id_solicitacao}
        ).fetchone()

        if xml:
            url, expiracao = xml
            if expiracao > agora:
                resultado.append({
                    "id_solicitacao": s.id_solicitacao,
                    "data_inicio": s.data_inicio,
                    "data_fim": s.data_fim,
                    "status": "concluido",
                    "xml_url": url,
                    "data_solicitacao": s.data_solicitacao
                })
        else:
            # Se ainda não tem XML, mantém como pendente (mostrar no frontend)
            resultado.append({
                "id_solicitacao": s.id_solicitacao,
                "data_inicio": s.data_inicio,
                "data_fim": s.data_fim,
                "status": s.status,
                "xml_url": None,
                "data_solicitacao": s.data_solicitacao
            })

    return resultado

class ExclusaoSolicitacao(BaseModel):
    id_solicitacao: int

@router.delete("/solicitacoes")
def deletar_solicitacao(payload: ExclusaoSolicitacao, db: Session = Depends(get_db)):
    id_solicitacao = payload.id_solicitacao
    # 🔍 Verifica se a solicitação existe
    solicitacao = db.query(Solicitacao).filter(Solicitacao.id_solicitacao == id_solicitacao).first()

    if not solicitacao:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")

    # 🗑️ Exclui primeiro o XML vinculado (se houver)
    db.execute(
        text("DELETE FROM xmls WHERE id_solicitacao = :id"),
        {"id": id_solicitacao}
    )

    # 🗑️ Agora exclui a solicitação da tabela
    db.delete(solicitacao)
    db.commit()

    return {"status": "Solicitação deletada com sucesso", "id_solicitacao": id_solicitacao}
