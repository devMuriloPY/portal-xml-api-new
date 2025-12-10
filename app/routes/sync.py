from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel, Field, validator
from datetime import datetime, timedelta
from typing import Optional, List
import re

from app.db.database import get_db
from app.models.contador import Contador
from app.models.cliente import Cliente
from app.models.xmls import XML
from app.models.solicitacao import Solicitacao
from app.utils.cnpj_mask import formatar_cnpj, limpar_cnpj

# Router para endpoints de sincronização
# NOTA: Estas rotas NÃO requerem autenticação, pois são usadas pelo sincronizador
router = APIRouter()


# ==================== SCHEMAS ====================

# Clientes
class SincronizarClienteRequest(BaseModel):
    nome: str
    telefone: Optional[str] = None
    celular: Optional[str] = None
    email: Optional[str] = None
    cnpj: str
    contador_cnpj: str
    atualizar: bool = False

    @validator('cnpj')
    def validar_cnpj(cls, v):
        cnpj_limpo = limpar_cnpj(v)
        if len(cnpj_limpo) != 14:
            raise ValueError('CNPJ deve ter 14 dígitos')
        return formatar_cnpj(cnpj_limpo)

    @validator('contador_cnpj')
    def validar_contador_cnpj(cls, v):
        cnpj_limpo = limpar_cnpj(v)
        if len(cnpj_limpo) != 14:
            raise ValueError('CNPJ do contador deve ter 14 dígitos')
        return formatar_cnpj(cnpj_limpo)


class ClienteResponse(BaseModel):
    id_cliente: int
    nome: Optional[str]
    telefone: Optional[str]
    celular: Optional[str]
    email: Optional[str]
    cnpj: str
    id_contador: int

    class Config:
        from_attributes = True


# Contadores
class SincronizarContadorItem(BaseModel):
    nome: Optional[str] = None
    cnpj: str
    email: Optional[str] = None

    @validator('cnpj')
    def validar_cnpj(cls, v):
        cnpj_limpo = limpar_cnpj(v)
        if len(cnpj_limpo) != 14:
            raise ValueError('CNPJ deve ter 14 dígitos')
        return formatar_cnpj(cnpj_limpo)


class SincronizarContadorRequest(BaseModel):
    nome: Optional[str] = None
    cnpj: Optional[str] = None
    email: Optional[str] = None
    atualizar: bool = False
    contadores: Optional[List[SincronizarContadorItem]] = None

    @validator('cnpj')
    def validar_cnpj_se_fornecido(cls, v):
        if v is not None and v != "":
            cnpj_limpo = limpar_cnpj(v)
            if len(cnpj_limpo) != 14:
                raise ValueError('CNPJ deve ter 14 dígitos')
            return formatar_cnpj(cnpj_limpo)
        return v


class ContadorResponse(BaseModel):
    id_contador: int
    nome: Optional[str]
    cnpj: str
    email: Optional[str]

    class Config:
        from_attributes = True


# XMLs
class InserirXMLRequest(BaseModel):
    id_cliente: int
    nome_arquivo: str
    url_arquivo: str
    id_solicitacao: Optional[int] = None
    data_envio: Optional[datetime] = None
    expiracao: Optional[datetime] = None


class XMLResponse(BaseModel):
    id_xml: int
    id_cliente: int
    nome_arquivo: str
    url_arquivo: str
    data_envio: Optional[datetime]
    expiracao: Optional[datetime]
    id_solicitacao: Optional[int]

    class Config:
        from_attributes = True


# Solicitações
class AtualizarStatusSolicitacaoRequest(BaseModel):
    id_solicitacao: int
    novo_status: str

    @validator('novo_status')
    def validar_status(cls, v):
        status_validos = ['em_processamento', 'concluida', 'erro']
        if v not in status_validos:
            raise ValueError(f'novo_status deve ser um dos valores: {", ".join(status_validos)}')
        return v


# ==================== ENDPOINTS DE CLIENTES ====================

@router.post("/clientes/sincronizar")
async def sincronizar_cliente(
    dados: SincronizarClienteRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Sincroniza um cliente do SQL Server local para a nuvem.
    Se o cliente já existir, pode criar ou atualizar conforme parâmetro.
    """
    try:
        # 1. Verificar/criar contador
        result_contador = await db.execute(
            select(Contador).where(Contador.cnpj == dados.contador_cnpj)
        )
        contador = result_contador.scalars().first()

        if not contador:
            # Criar contador apenas com CNPJ
            contador = Contador(
                cnpj=dados.contador_cnpj,
                nome=None,
                email=None
            )
            db.add(contador)
            await db.flush()  # Para obter o ID

        # 2. Verificar se cliente existe
        result_cliente = await db.execute(
            select(Cliente).where(Cliente.cnpj == dados.cnpj)
        )
        cliente = result_cliente.scalars().first()

        acao = "ja_existia"
        if not cliente:
            # Criar cliente
            cliente = Cliente(
                nome=dados.nome,
                telefone=dados.telefone,
                celular=dados.celular,
                email=dados.email,
                cnpj=dados.cnpj,
                id_contador=contador.id_contador
            )
            db.add(cliente)
            await db.commit()
            await db.refresh(cliente)
            acao = "criado"
        elif dados.atualizar:
            # Atualizar cliente existente
            cliente.nome = dados.nome
            cliente.telefone = dados.telefone
            cliente.celular = dados.celular
            cliente.email = dados.email
            cliente.id_contador = contador.id_contador
            await db.commit()
            acao = "atualizado"

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Cliente sincronizado com sucesso",
                "data": {
                    "id_cliente": cliente.id_cliente,
                    "id_contador": contador.id_contador,
                    "acao": acao
                }
            }
        )

    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Erro de validação",
                "errors": [str(e)]
            }
        )
    except SQLAlchemyError as e:
        await db.rollback()
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Erro ao sincronizar cliente",
                "error": str(e)
            }
        )


@router.get("/clientes/por-cnpj/{cnpj}")
async def buscar_cliente_por_cnpj(
    cnpj: str,
    db: AsyncSession = Depends(get_db)
):
    """Retorna o ID e dados do cliente baseado no CNPJ."""
    try:
        cnpj_formatado = formatar_cnpj(cnpj)
        result = await db.execute(
            select(Cliente).where(Cliente.cnpj == cnpj_formatado)
        )
        cliente = result.scalars().first()

        if not cliente:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": "Cliente não encontrado para o CNPJ informado"
                }
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "id_cliente": cliente.id_cliente,
                    "nome": cliente.nome,
                    "telefone": cliente.telefone,
                    "celular": cliente.celular,
                    "email": cliente.email,
                    "cnpj": cliente.cnpj,
                    "id_contador": cliente.id_contador
                }
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Erro ao buscar cliente",
                "error": str(e)
            }
        )


@router.get("/clientes/{id}")
async def buscar_cliente_por_id(
    id: int,
    db: AsyncSession = Depends(get_db)
):
    """Retorna os dados completos do cliente pelo ID."""
    try:
        result = await db.execute(
            select(Cliente).where(Cliente.id_cliente == id)
        )
        cliente = result.scalars().first()

        if not cliente:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": "Cliente não encontrado"
                }
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "id_cliente": cliente.id_cliente,
                    "nome": cliente.nome,
                    "telefone": cliente.telefone,
                    "celular": cliente.celular,
                    "email": cliente.email,
                    "cnpj": cliente.cnpj,
                    "id_contador": cliente.id_contador
                }
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Erro ao buscar cliente",
                "error": str(e)
            }
        )


# ==================== ENDPOINTS DE CONTADORES ====================

@router.post("/contadores/sincronizar")
async def sincronizar_contador(
    dados: SincronizarContadorRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Sincroniza um ou múltiplos contadores do SQL Server local para a nuvem.
    """
    try:
        # Normalizar para lista
        if dados.contadores:
            contadores_list = dados.contadores
        elif dados.cnpj:
            # Se recebeu um único objeto, processa como array com um item
            contadores_list = [SincronizarContadorItem(
                nome=dados.nome,
                cnpj=dados.cnpj,
                email=dados.email
            )]
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "CNPJ ou lista de contadores é obrigatório",
                    "errors": ["Deve fornecer cnpj ou contadores"]
                }
            )

        processados = 0
        criados = 0
        atualizados = 0
        ja_existiam = 0
        detalhes = []

        for contador_data in contadores_list:
            processados += 1

            # Verificar se contador existe
            result = await db.execute(
                select(Contador).where(Contador.cnpj == contador_data.cnpj)
            )
            contador = result.scalars().first()

            acao = "ja_existia"
            if not contador:
                # Criar contador
                contador = Contador(
                    nome=contador_data.nome,
                    cnpj=contador_data.cnpj,
                    email=contador_data.email
                )
                db.add(contador)
                await db.flush()
                await db.refresh(contador)
                criados += 1
                acao = "criado"
            elif dados.atualizar:
                # Atualizar contador existente
                contador.nome = contador_data.nome
                contador.email = contador_data.email
                atualizados += 1
                acao = "atualizado"
            else:
                ja_existiam += 1

            detalhes.append({
                "cnpj": contador.cnpj,
                "id_contador": contador.id_contador,
                "acao": acao
            })

        await db.commit()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Contadores sincronizados com sucesso",
                "data": {
                    "processados": processados,
                    "criados": criados,
                    "atualizados": atualizados,
                    "ja_existiam": ja_existiam,
                    "detalhes": detalhes
                }
            }
        )

    except ValueError as e:
        await db.rollback()
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Erro de validação",
                "errors": [str(e)]
            }
        )
    except SQLAlchemyError as e:
        await db.rollback()
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Erro ao sincronizar contadores",
                "error": str(e)
            }
        )


@router.get("/contadores")
async def listar_contadores(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """Retorna lista de todos os contadores."""
    try:
        # Buscar total de contadores
        result_total = await db.execute(select(Contador))
        total = len(result_total.scalars().all())

        # Buscar contadores com paginação
        result = await db.execute(
            select(Contador)
            .order_by(Contador.id_contador)
            .limit(limit)
            .offset(offset)
        )
        contadores = result.scalars().all()

        contadores_data = []
        for contador in contadores:
            contadores_data.append({
                "id_contador": contador.id_contador,
                "nome": contador.nome,
                "cnpj": contador.cnpj,
                "email": contador.email
            })

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "contadores": contadores_data
                }
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Erro ao listar contadores",
                "error": str(e)
            }
        )


@router.get("/contadores/por-cnpj/{cnpj}")
async def buscar_contador_por_cnpj(
    cnpj: str,
    db: AsyncSession = Depends(get_db)
):
    """Retorna o ID e dados do contador baseado no CNPJ."""
    try:
        cnpj_formatado = formatar_cnpj(cnpj)
        result = await db.execute(
            select(Contador).where(Contador.cnpj == cnpj_formatado)
        )
        contador = result.scalars().first()

        if not contador:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": "Contador não encontrado para o CNPJ informado"
                }
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "id_contador": contador.id_contador,
                    "nome": contador.nome,
                    "cnpj": contador.cnpj,
                    "email": contador.email
                }
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Erro ao buscar contador",
                "error": str(e)
            }
        )


# ==================== ENDPOINTS DE XMLs ====================

@router.post("/xmls/arquivo")
async def inserir_xml_arquivo(
    dados: InserirXMLRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Registra informações sobre um arquivo XML enviado para o S3.
    """
    try:
        # Validar se o cliente existe
        result_cliente = await db.execute(
            select(Cliente).where(Cliente.id_cliente == dados.id_cliente)
        )
        cliente = result_cliente.scalars().first()

        if not cliente:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": "Cliente não encontrado"
                }
            )

        # Calcular data_envio e expiracao
        data_envio = dados.data_envio or datetime.now()
        if dados.expiracao:
            expiracao = dados.expiracao
        else:
            expiracao = data_envio + timedelta(hours=24)

        # Criar registro XML
        novo_xml = XML(
            id_cliente=dados.id_cliente,
            nome_arquivo=dados.nome_arquivo,
            url_arquivo=dados.url_arquivo,
            data_envio=data_envio,
            expiracao=expiracao,
            id_solicitacao=dados.id_solicitacao
        )
        db.add(novo_xml)
        await db.commit()
        await db.refresh(novo_xml)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Informações do arquivo XML registradas com sucesso",
                "data": {
                    "id_xml": novo_xml.id_xml,
                    "id_cliente": novo_xml.id_cliente,
                    "nome_arquivo": novo_xml.nome_arquivo,
                    "data_envio": novo_xml.data_envio.isoformat() if novo_xml.data_envio else None,
                    "expiracao": novo_xml.expiracao.isoformat() if novo_xml.expiracao else None
                }
            }
        )

    except SQLAlchemyError as e:
        await db.rollback()
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Erro ao registrar arquivo XML",
                "error": str(e)
            }
        )


@router.get("/xmls/cliente/{id_cliente}")
async def buscar_xmls_por_cliente(
    id_cliente: int,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """
    Retorna lista de arquivos XML de um cliente.
    """
    try:
        # Verificar se cliente existe
        result_cliente = await db.execute(
            select(Cliente).where(Cliente.id_cliente == id_cliente)
        )
        cliente = result_cliente.scalars().first()

        if not cliente:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": "Cliente não encontrado"
                }
            )

        # Buscar XMLs
        result_total = await db.execute(
            select(XML).where(XML.id_cliente == id_cliente)
        )
        total = len(result_total.scalars().all())

        result = await db.execute(
            select(XML)
            .where(XML.id_cliente == id_cliente)
            .order_by(desc(XML.data_envio))
            .limit(limit)
            .offset(offset)
        )
        xmls = result.scalars().all()

        xmls_data = []
        for xml in xmls:
            xmls_data.append({
                "id_xml": xml.id_xml,
                "id_cliente": xml.id_cliente,
                "nome_arquivo": xml.nome_arquivo,
                "url_arquivo": xml.url_arquivo,
                "data_envio": xml.data_envio.isoformat() if xml.data_envio else None,
                "expiracao": xml.expiracao.isoformat() if xml.expiracao else None,
                "id_solicitacao": xml.id_solicitacao
            })

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "xmls": xmls_data
                }
            }
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Erro ao buscar XMLs",
                "error": str(e)
            }
        )


# ==================== ENDPOINTS DE SOLICITAÇÕES ====================

@router.put("/auth/solicitacoes/status")
async def atualizar_status_solicitacao(
    dados: AtualizarStatusSolicitacaoRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Atualiza o status de uma solicitação de processamento de XML.
    """
    try:
        # Buscar solicitação
        result = await db.execute(
            select(Solicitacao).where(Solicitacao.id_solicitacao == dados.id_solicitacao)
        )
        solicitacao = result.scalars().first()

        if not solicitacao:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": "Solicitação não encontrada"
                }
            )

        status_anterior = solicitacao.status
        solicitacao.status = dados.novo_status
        await db.commit()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Status da solicitação atualizado com sucesso",
                "data": {
                    "id_solicitacao": solicitacao.id_solicitacao,
                    "status_anterior": status_anterior,
                    "status_atual": dados.novo_status
                }
            }
        )

    except ValueError as e:
        await db.rollback()
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Status inválido",
                "errors": ["novo_status deve ser um dos valores: em_processamento, concluida, erro"]
            }
        )
    except SQLAlchemyError as e:
        await db.rollback()
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Erro ao atualizar status da solicitação",
                "error": str(e)
            }
        )

