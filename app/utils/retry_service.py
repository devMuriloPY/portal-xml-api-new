import asyncio
from sqlalchemy import select
from datetime import datetime, timedelta
from app.db.database import async_session
from app.models.solicitacao import Solicitacao
from app.models.cliente import Cliente
from app.routes.websocket import conexoes_ativas

class RetryService:
    def __init__(self):
        self.is_running = False
        self.task = None
    
    async def start(self):
        """Inicia o sistema de retry"""
        if not self.is_running:
            self.is_running = True
            self.task = asyncio.create_task(self._retry_loop())
    
    async def stop(self):
        """Para o sistema de retry"""
        if self.is_running:
            self.is_running = False
            if self.task:
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass
    
    async def _retry_loop(self):
        """Loop principal do sistema de retry"""
        while self.is_running:
            try:
                await self._process_pending_requests()
            except Exception as e:
                pass  # Log error if needed
            await asyncio.sleep(10)  # Aguardar 10 segundos
    
    async def _process_pending_requests(self):
        """Processa solicitações pendentes"""
        async with async_session() as db:
            # Buscar solicitações pendentes há mais de 10 segundos
            result = await db.execute(
                select(Solicitacao).where(
                    Solicitacao.status == "pendente",
                    Solicitacao.data_solicitacao < datetime.utcnow() - timedelta(seconds=10)
                )
            )
            solicitacoes_pendentes = result.scalars().all()
            
            for solicitacao in solicitacoes_pendentes:
                await self._process_single_request(solicitacao, db)
    
    async def _process_single_request(self, solicitacao, db):
        """Processa uma única solicitação pendente"""
        # Buscar cliente para notificar
        result_cliente = await db.execute(
            select(Cliente).where(Cliente.id_cliente == solicitacao.id_cliente)
        )
        cliente = result_cliente.scalars().first()
        
        if cliente and cliente.id_cliente in conexoes_ativas:
            # Tentar enviar novamente via WebSocket
            websocket_client = conexoes_ativas[cliente.id_cliente]
            try:
                await websocket_client.send_json({
                    "id_cliente": cliente.id_cliente,
                    "data_inicio": str(solicitacao.data_inicio),
                    "data_fim": str(solicitacao.data_fim),
                    "id_solicitacao": solicitacao.id_solicitacao,
                    "retry": True
                })
            except Exception as e:
                await self._increment_retry_count(solicitacao, db)
        else:
            # Cliente não conectado, incrementar tentativas
            await self._increment_retry_count(solicitacao, db)
    
    async def _increment_retry_count(self, solicitacao, db):
        """Incrementa contador de tentativas e marca como 'sem_conexao' se necessário"""
        if not hasattr(solicitacao, 'tentativas'):
            solicitacao.tentativas = 0
        solicitacao.tentativas += 1
        
        if solicitacao.tentativas >= 3:
            solicitacao.status = "sem_conexao"
        
        await db.commit()

# Instância global do serviço
retry_service = RetryService()