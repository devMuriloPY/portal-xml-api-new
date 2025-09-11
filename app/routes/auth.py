from fastapi import APIRouter, Depends, HTTPException, status, Response
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

from app.db.database import get_db
from app.models.contador import Contador
from app.models.cliente import Cliente
from app.models.solicitacao import Solicitacao
from app.utils.security import gerar_hash_senha, verificar_senha
from app.utils.email_utils import enviar_email, renderizar_template_email
from app.utils.cnpj_mask import formatar_cnpj
from app.routes.websocket import conexoes_ativas

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
RESET_TOKEN_EXPIRE_MINUTES = 30
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://www.portalxml.wmsistemas.inf.br/")

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def agora_brasil():
    # Retorna um datetime sem fuso horário (offset-naive)
    return datetime.now().replace(tzinfo=None)

def converter_data_segura(data_str: str) -> datetime.date:
    return datetime.strptime(data_str, "%Y-%m-%d").date()

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

# �� Login
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

# �� Autenticação
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

# �� Dados do contador
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

# �� Solicitar redefinição
@router.post("/solicitar-redefinicao")
async def solicitar_redefinicao(dados: SolicitarRedefinicao, db: AsyncSession = Depends(get_db)):
    identificador = dados.identificador.strip()

    if "@" in identificador:
        result = await db.execute(select(Contador).where(Contador.email == identificador))
    else:
        cnpj_formatado = formatar_cnpj(identificador)
        result = await db.execute(select(Contador).where(Contador.cnpj == cnpj_formatado))

    contador = result.scalars().first()

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
async def redefinir_senha(dados: RedefinirSenha, db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(dados.token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
    except:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")

    result = await db.execute(select(Contador).where(Contador.email == email))
    contador = result.scalars().first()

    if not contador:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if dados.nova_senha != dados.confirmar_senha:
        raise HTTPException(status_code=400, detail="As senhas não coincidem")

    contador.senha_hash = gerar_hash_senha(dados.nova_senha)
    await db.commit()

    return {"mensagem": "Senha redefinida com sucesso"}

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

# �� Criar solicitação
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

        data_solicitacao = s.data_solicitacao.isoformat()

        resposta.append({
            "id_solicitacao": s.id_solicitacao,
            "data_inicio": s.data_inicio,
            "data_fim": s.data_fim,
            "status": "concluido" if xml_data and xml_data[1] > agora else s.status,
            "xml_url": xml_data[0] if xml_data and xml_data[1] > agora else None,
            "data_solicitacao": data_solicitacao,
            "valor_nfe_autorizadas": xml_data[2],
            "valor_nfe_canceladas": xml_data[3],
            "valor_nfc_autorizadas": xml_data[4],
            "valor_nfc_canceladas": xml_data[5],
            "quantidade_nfe_autorizadas": xml_data[6],
            "quantidade_nfe_canceladas": xml_data[7],
            "quantidade_nfc_autorizadas": xml_data[8],
            "quantidade_nfc_canceladas": xml_data[9]
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