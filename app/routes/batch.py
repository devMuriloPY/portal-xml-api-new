from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func, and_, or_
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel, validator
from datetime import datetime, timedelta, date
from typing import List, Optional
import secrets
import asyncio
import uuid

from app.db.database import get_db
from app.models.contador import Contador
from app.models.cliente import Cliente
from app.models.solicitacao import Solicitacao
from app.models.batch_request import BatchRequest, BatchRequestItem
from app.routes.auth import obter_contador_logado
from app.routes.websocket import conexoes_ativas
from app.services.batch_processor import batch_processor
from app.utils.batch_validators import BatchValidator, BatchValidationError

router = APIRouter()

# Rate limiting storage (em produção, usar Redis)
user_batch_limits = {}
user_last_batch = {}

# Schemas
class CriarSolicitacaoLote(BaseModel):
    client_ids: List[str]
    data_inicio: str
    data_fim: str

    @validator('client_ids')
    def validate_client_ids(cls, v):
        try:
            BatchValidator.validate_client_ids(v)
        except BatchValidationError as e:
            raise ValueError(e.message)
        return v

    @validator('data_inicio', 'data_fim')
    def validate_dates(cls, v):
        try:
            return datetime.strptime(v, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError('Formato de data inválido. Use YYYY-MM-DD')

    def validate_date_range(self):
        try:
            BatchValidator.validate_dates(self.data_inicio.isoformat(), self.data_fim.isoformat())
        except BatchValidationError as e:
            raise ValueError(e.message)

class BatchResponse(BaseModel):
    batch_id: str
    status: str
    total_requests: int
    requests: List[dict]
    created_at: datetime

class BatchStatusResponse(BaseModel):
    batch_id: str
    status: str
    total_requests: int
    completed_requests: int
    failed_requests: int
    requests: List[dict]
    created_at: datetime

class BatchListResponse(BaseModel):
    batches: List[dict]
    pagination: dict

# Funções auxiliares
def gerar_id_batch() -> str:
    """Gera um ID único para o lote"""
    return f"batch_{uuid.uuid4().hex[:12]}"

def gerar_id_item() -> str:
    """Gera um ID único para o item do lote"""
    return f"req_{uuid.uuid4().hex[:8]}"

def converter_data_segura(data_str: str) -> date:
    """Converte string de data para date object"""
    return datetime.strptime(data_str, "%Y-%m-%d").date()

def agora_brasil():
    """Retorna um datetime sem fuso horário (offset-naive)"""
    return datetime.now().replace(tzinfo=None)

async def verificar_rate_limit(user_id: str) -> bool:
    """Verifica se o usuário pode criar um novo lote"""
    now = datetime.now()
    
    # Verificar limite de lotes simultâneos (máximo 5)
    active_batches = await get_active_batches_count(user_id)
    if active_batches >= 5:
        return False
    
    # Verificar intervalo mínimo entre lotes (30 segundos)
    if user_id in user_last_batch:
        time_diff = now - user_last_batch[user_id]
        if time_diff.total_seconds() < 30:
            return False
    
    return True

async def get_active_batches_count(user_id: str) -> int:
    """Conta lotes ativos do usuário"""
    from app.db.database import async_session
    async with async_session() as db:
        result = await db.execute(
            select(func.count()).select_from(
                select(BatchRequest).where(
                    and_(
                        BatchRequest.user_id == user_id,
                        BatchRequest.status.in_(["pending", "processing"])
                    )
                ).subquery()
            )
        )
        return result.scalar() or 0

async def verificar_clientes_online(client_ids: List[str]) -> List[str]:
    """Verifica quais clientes estão online via WebSocket"""
    clientes_online = []
    for client_id in client_ids:
        # Converter para int para verificar na conexoes_ativas
        try:
            client_id_int = int(client_id)
            if client_id_int in conexoes_ativas:
                clientes_online.append(client_id)
        except ValueError:
            # Se não conseguir converter, pular
            continue
    return clientes_online


# Endpoints

@router.get("/clientes-online")
async def listar_clientes_online():
    """Lista clientes conectados via WebSocket"""
    return {
        "clientes_conectados": list(conexoes_ativas.keys()),
        "total_conectados": len(conexoes_ativas)
    }

@router.post("/solicitacoes/batch", response_model=BatchResponse, status_code=201)
async def criar_solicitacao_lote(
    dados: CriarSolicitacaoLote,
    contador: Contador = Depends(obter_contador_logado),
    db: AsyncSession = Depends(get_db)
):
    """Criar solicitação em lote"""
    try:
        # Validar período
        dados.validate_date_range()
        
        # Verificar rate limiting
        user_id = str(contador.id_contador)
        if not await verificar_rate_limit(user_id):
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": "Muitas solicitações em lote. Aguarde antes de criar um novo lote."
                }
            )
        
        # Verificar se todos os clientes pertencem ao contador
        result = await db.execute(
            select(Cliente).where(
                and_(
                    Cliente.id_contador == contador.id_contador,
                    Cliente.id_cliente.in_([int(cid) for cid in dados.client_ids])
                )
            )
        )
        clientes = result.scalars().all()
        
        if len(clientes) != len(dados.client_ids):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "validation_error",
                    "message": "Alguns clientes não pertencem ao usuário ou não existem",
                    "details": {
                        "client_ids": ["Cliente não encontrado ou não autorizado"]
                    }
                }
            )
        
        # Verificar clientes online
        clientes_online = await verificar_clientes_online(dados.client_ids)
        if not clientes_online:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "validation_error",
                    "message": "Nenhum cliente está online",
                    "details": {
                        "client_ids": ["Todos os clientes devem estar online para processamento em lote"]
                    }
                }
            )
        
        # Criar lote
        batch_id = gerar_id_batch()
        batch = BatchRequest(
            id=batch_id,
            user_id=user_id,
            status="pending",
            total_requests=len(dados.client_ids),
            data_inicio=dados.data_inicio,
            data_fim=dados.data_fim
        )
        
        db.add(batch)
        await db.commit()
        await db.refresh(batch)
        
        # Criar itens do lote
        items = []
        for cliente in clientes:
            item_id = gerar_id_item()
            item = BatchRequestItem(
                id=item_id,
                batch_id=batch_id,
                client_id=str(cliente.id_cliente),
                client_name=cliente.nome,
                status="pending"
            )
            db.add(item)
            items.append({
                "id": item_id,
                "client_id": str(cliente.id_cliente),
                "client_name": cliente.nome,
                "status": "pending",
                "created_at": batch.created_at.isoformat() + "Z"
            })
        
        await db.commit()
        
        # Atualizar último lote do usuário
        user_last_batch[user_id] = datetime.now()
        
        # Iniciar processamento assíncrono
        await batch_processor.process_batch(batch_id)
        
        return BatchResponse(
            batch_id=batch_id,
            status="pending",
            total_requests=len(dados.client_ids),
            requests=items,
            created_at=batch.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno: {str(e)}"
        )

@router.get("/solicitacoes/batch/{batch_id}", response_model=BatchStatusResponse)
async def consultar_status_lote(
    batch_id: str,
    contador: Contador = Depends(obter_contador_logado),
    db: AsyncSession = Depends(get_db)
):
    """Consultar status do lote"""
    # Buscar lote
    result = await db.execute(
        select(BatchRequest).where(
            and_(
                BatchRequest.id == batch_id,
                BatchRequest.user_id == str(contador.id_contador)
            )
        )
    )
    batch = result.scalars().first()
    
    if not batch:
        raise HTTPException(status_code=404, detail="Lote não encontrado")
    
    # Buscar itens do lote
    result = await db.execute(
        select(BatchRequestItem).where(BatchRequestItem.batch_id == batch_id)
        .order_by(BatchRequestItem.created_at)
    )
    items = result.scalars().all()
    
    # Montar resposta dos itens
    requests = []
    for item in items:
        item_data = {
            "id": item.id,
            "client_id": item.client_id,
            "client_name": item.client_name,
            "status": item.status,
            "created_at": item.created_at.isoformat() + "Z"
        }
        
        if item.status == "completed" and item.xml_url:
            item_data["xml_url"] = item.xml_url
            item_data["completed_at"] = item.completed_at.isoformat() + "Z"
        elif item.status == "error" and item.error_message:
            item_data["error_message"] = item.error_message
            item_data["completed_at"] = item.completed_at.isoformat() + "Z"
        
        requests.append(item_data)
    
    return BatchStatusResponse(
        batch_id=batch.id,
        status=batch.status,
        total_requests=batch.total_requests,
        completed_requests=batch.completed_requests,
        failed_requests=batch.failed_requests,
        requests=requests,
        created_at=batch.created_at
    )

@router.get("/solicitacoes/batch", response_model=BatchListResponse)
async def listar_lotes(
    page: int = 1,
    limit: int = 10,
    status_filter: str = "all",
    contador: Contador = Depends(obter_contador_logado),
    db: AsyncSession = Depends(get_db)
):
    """Listar lotes do usuário"""
    try:
        # Validar parâmetros
        page, limit = BatchValidator.validate_pagination_params(page, limit)
        status_filter = BatchValidator.validate_status_filter(status_filter)
    except BatchValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "validation_error",
                "message": e.message,
                "details": e.details
            }
        )
    
    # Construir query
    query = select(BatchRequest).where(BatchRequest.user_id == str(contador.id_contador))
    
    if status_filter != "all":
        query = query.where(BatchRequest.status == status_filter)
    
    # Contar total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_items = total_result.scalar()
    
    # Buscar lotes com paginação
    query = query.order_by(BatchRequest.created_at.desc())
    query = query.offset((page - 1) * limit).limit(limit)
    
    result = await db.execute(query)
    batches = result.scalars().all()
    
    # Montar resposta
    batch_list = []
    for batch in batches:
        batch_data = {
            "batch_id": batch.id,
            "status": batch.status,
            "total_requests": batch.total_requests,
            "completed_requests": batch.completed_requests,
            "failed_requests": batch.failed_requests,
            "created_at": batch.created_at.isoformat() + "Z"
        }
        
        if batch.completed_at:
            batch_data["completed_at"] = batch.completed_at.isoformat() + "Z"
        
        batch_list.append(batch_data)
    
    total_pages = (total_items + limit - 1) // limit
    
    return BatchListResponse(
        batches=batch_list,
        pagination={
            "current_page": page,
            "total_pages": total_pages,
            "total_items": total_items,
            "items_per_page": limit
        }
    )

@router.delete("/solicitacoes/batch/{batch_id}")
async def cancelar_lote(
    batch_id: str,
    contador: Contador = Depends(obter_contador_logado),
    db: AsyncSession = Depends(get_db)
):
    """Cancelar lote (opcional)"""
    # Buscar lote
    result = await db.execute(
        select(BatchRequest).where(
            and_(
                BatchRequest.id == batch_id,
                BatchRequest.user_id == str(contador.id_contador)
            )
        )
    )
    batch = result.scalars().first()
    
    if not batch:
        raise HTTPException(status_code=404, detail="Lote não encontrado")
    
    # Verificar se pode ser cancelado
    if batch.status in ["completed", "error"]:
        raise HTTPException(
            status_code=400,
            detail="Lote já foi concluído e não pode ser cancelado"
        )
    
    # Atualizar status para cancelado (usando 'error' como status de cancelamento)
    batch.status = "error"
    batch.completed_at = agora_brasil()
    
    # Atualizar itens pendentes
    result = await db.execute(
        select(BatchRequestItem).where(
            and_(
                BatchRequestItem.batch_id == batch_id,
                BatchRequestItem.status == "pending"
            )
        )
    )
    items = result.scalars().all()
    
    for item in items:
        item.status = "error"
        item.error_message = "Lote cancelado pelo usuário"
        item.completed_at = agora_brasil()
    
    await db.commit()
    
    return {
        "message": "Batch cancelado com sucesso",
        "batch_id": batch_id
    }
