import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.db.database import async_session
from app.models.batch_request import BatchRequest, BatchRequestItem
from app.models.solicitacao import Solicitacao
from app.routes.websocket import conexoes_ativas

logger = logging.getLogger(__name__)

class BatchProcessor:
    def __init__(self):
        self.running = False
        self.processing_tasks: Dict[str, asyncio.Task] = {}
        self.max_concurrent_batches = 10
        self.item_timeout = 30 * 60  # 30 minutos por item
        
    async def start(self):
        """Inicia o processador de lotes"""
        self.running = True
        logger.info("Batch processor started")
        
        # Iniciar task de limpeza de lotes antigos
        asyncio.create_task(self._cleanup_old_batches())
        
    async def stop(self):
        """Para o processador de lotes"""
        self.running = False
        
        # Cancelar todas as tasks em execução
        for task in self.processing_tasks.values():
            if not task.done():
                task.cancel()
        
        # Aguardar cancelamento
        if self.processing_tasks:
            await asyncio.gather(*self.processing_tasks.values(), return_exceptions=True)
        
        logger.info("Batch processor stopped")
    
    async def process_batch(self, batch_id: str):
        """Processa um lote específico"""
        if batch_id in self.processing_tasks:
            logger.warning(f"Batch {batch_id} is already being processed")
            return
        
        # Verificar limite de concorrência
        if len(self.processing_tasks) >= self.max_concurrent_batches:
            logger.warning(f"Maximum concurrent batches reached ({self.max_concurrent_batches})")
            return
        
        # Criar task de processamento
        task = asyncio.create_task(self._process_batch_async(batch_id))
        self.processing_tasks[batch_id] = task
        
        try:
            await task
        except asyncio.CancelledError:
            logger.info(f"Batch {batch_id} processing was cancelled")
        except Exception as e:
            logger.error(f"Error processing batch {batch_id}: {e}")
        finally:
            # Remover task da lista
            self.processing_tasks.pop(batch_id, None)
    
    async def _process_batch_async(self, batch_id: str):
        """Processa o lote de forma assíncrona"""
        async with async_session() as db:
            try:
                # Buscar o lote
                result = await db.execute(
                    select(BatchRequest).where(BatchRequest.id == batch_id)
                )
                batch = result.scalars().first()
                
                if not batch:
                    logger.error(f"Batch {batch_id} not found")
                    return
                
                # Verificar se já está sendo processado ou concluído
                if batch.status in ["processing", "completed", "error"]:
                    logger.info(f"Batch {batch_id} is already {batch.status}")
                    return
                
                # Atualizar status para processing
                batch.status = "processing"
                await db.commit()
                
                # Buscar itens pendentes
                result = await db.execute(
                    select(BatchRequestItem).where(
                        and_(
                            BatchRequestItem.batch_id == batch_id,
                            BatchRequestItem.status == "pending"
                        )
                    ).order_by(BatchRequestItem.created_at)
                )
                items = result.scalars().all()
                
                logger.info(f"Processing batch {batch_id} with {len(items)} items")
                
                # Processar cada item
                for item in items:
                    try:
                        await self._process_item_with_timeout(db, item, batch)
                    except Exception as e:
                        logger.error(f"Error processing item {item.id}: {e}")
                        await self._mark_item_error(db, item, batch, str(e))
                
                # Verificar status final do lote
                await self._update_batch_final_status(db, batch)
                
                logger.info(f"Batch {batch_id} processing completed")
                
            except Exception as e:
                logger.error(f"Error in batch processing {batch_id}: {e}")
                # Marcar lote como erro
                try:
                    batch.status = "error"
                    batch.completed_at = datetime.now()
                    await db.commit()
                except:
                    pass
    
    async def _process_item_with_timeout(self, db: AsyncSession, item: BatchRequestItem, batch: BatchRequest):
        """Processa um item com timeout"""
        try:
            # Usar asyncio.wait_for para timeout
            await asyncio.wait_for(
                self._process_single_item(db, item, batch),
                timeout=self.item_timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Item {item.id} timed out after {self.item_timeout} seconds")
            await self._mark_item_error(db, item, batch, "Timeout - item demorou muito para processar")
    
    async def _process_single_item(self, db: AsyncSession, item: BatchRequestItem, batch: BatchRequest):
        """Processa um item individual do lote"""
        # Atualizar status para processing
        item.status = "processing"
        await db.commit()
        
        try:
            # Converter client_id para int
            client_id = int(item.client_id)
            
            # Criar solicitação individual usando a lógica existente (igual ao auth.py)
            data_inicio_api = batch.data_inicio + timedelta(days=1)
            data_fim_api = batch.data_fim + timedelta(days=1)
            
            data_inicio = batch.data_inicio
            data_fim = batch.data_fim
            
            nova_solicitacao = Solicitacao(
                id_cliente=client_id,
                data_inicio=data_inicio_api,
                data_fim=data_fim_api,
                status="pendente",
                data_solicitacao=datetime.now()
            )
            
            db.add(nova_solicitacao)
            await db.commit()
            await db.refresh(nova_solicitacao)
            
            # Simular processamento (em produção, aqui seria a lógica real)
            # Por exemplo, chamar API externa, processar XML, etc.
            await asyncio.sleep(1)  # Simular tempo de processamento
            
            # Atualizar item como concluído
            item.status = "completed"
            item.xml_url = f"https://api.exemplo.com/xml/{nova_solicitacao.id_solicitacao}.xml"
            item.completed_at = datetime.now()
            
            # Atualizar contadores do lote
            batch.completed_requests += 1
            
            await db.commit()
            
            # Notificar via WebSocket
            await self._notify_websocket(item, nova_solicitacao, batch)
            
            logger.info(f"Item {item.id} completed successfully")
            
        except Exception as e:
            logger.error(f"Error processing item {item.id}: {e}")
            await self._mark_item_error(db, item, batch, str(e))
            raise
    
    async def _mark_item_error(self, db: AsyncSession, item: BatchRequestItem, batch: BatchRequest, error_message: str):
        """Marca um item como erro"""
        item.status = "error"
        item.error_message = error_message
        item.completed_at = datetime.now()
        
        # Atualizar contadores do lote
        batch.failed_requests += 1
        
        await db.commit()
        logger.info(f"Item {item.id} marked as error: {error_message}")
    
    async def _update_batch_final_status(self, db: AsyncSession, batch: BatchRequest):
        """Atualiza o status final do lote"""
        # Verificar se todos os itens foram processados
        result = await db.execute(
            select(func.count()).select_from(
                select(BatchRequestItem).where(
                    and_(
                        BatchRequestItem.batch_id == batch.id,
                        BatchRequestItem.status.in_(["completed", "error"])
                    )
                ).subquery()
            )
        )
        processed_count = result.scalar()
        
        if processed_count >= batch.total_requests:
            # Todos os itens foram processados
            if batch.failed_requests == 0:
                batch.status = "completed"
            elif batch.completed_requests == 0:
                batch.status = "error"
            else:
                batch.status = "completed"  # Alguns sucessos, alguns erros
            
            batch.completed_at = datetime.now()
            await db.commit()
            
            logger.info(f"Batch {batch.id} final status: {batch.status}")
    
    async def _notify_websocket(self, item: BatchRequestItem, solicitacao: Solicitacao, batch: BatchRequest):
        """Notifica via WebSocket"""
        try:
            websocket = conexoes_ativas.get(item.client_id)
            if websocket:
                await websocket.send_json({
                    "id_cliente": int(item.client_id),
                    "data_inicio": str(batch.data_inicio),
                    "data_fim": str(batch.data_fim),
                    "id_solicitacao": solicitacao.id_solicitacao,
                    "batch_id": batch.id,
                    "item_id": item.id,
                    "status": item.status
                })
                logger.info(f"WebSocket notification sent for item {item.id}")
        except Exception as e:
            logger.error(f"Error sending WebSocket notification for item {item.id}: {e}")
    
    async def _cleanup_old_batches(self):
        """Remove lotes antigos (24 horas)"""
        while self.running:
            try:
                await asyncio.sleep(3600)  # Executar a cada hora
                
                cutoff_time = datetime.now() - timedelta(hours=24)
                
                async with async_session() as db:
                    # Buscar lotes antigos
                    result = await db.execute(
                        select(BatchRequest).where(
                            and_(
                                BatchRequest.created_at < cutoff_time,
                                BatchRequest.status.in_(["completed", "error"])
                            )
                        )
                    )
                    old_batches = result.scalars().all()
                    
                    # Deletar lotes antigos (cascade vai deletar os itens)
                    for batch in old_batches:
                        await db.delete(batch)
                    
                    if old_batches:
                        await db.commit()
                        logger.info(f"Cleaned up {len(old_batches)} old batches")
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
    
    async def get_processing_status(self) -> Dict:
        """Retorna status do processador"""
        return {
            "running": self.running,
            "active_batches": len(self.processing_tasks),
            "max_concurrent": self.max_concurrent_batches,
            "processing_batch_ids": list(self.processing_tasks.keys())
        }

# Instância global do processador
batch_processor = BatchProcessor()
