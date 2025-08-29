from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import asyncio
from contextlib import asynccontextmanager

# Carregar variáveis de ambiente do .env
load_dotenv()

from app.routes import auth, websocket
from app.db.database import async_session
from app.models.solicitacao import Solicitacao
from app.models.cliente import Cliente
from sqlalchemy import select
from datetime import datetime, timedelta

# Sistema de retry para solicitações pendentes
async def tentar_reprocessar_solicitacoes():
    """Função para tentar reprocessar solicitações pendentes via WebSocket"""
    while True:
        try:
            # Buscar solicitações pendentes há mais de 10 segundos
            async with async_session() as db:
                result = await db.execute(
                    select(Solicitacao).where(
                        Solicitacao.status == "pendente",
                        Solicitacao.data_solicitacao < datetime.utcnow() - timedelta(seconds=10)
                    )
                )
                solicitacoes_pendentes = result.scalars().all()
                
                for solicitacao in solicitacoes_pendentes:
                    # Buscar cliente para notificar
                    result_cliente = await db.execute(
                        select(Cliente).where(Cliente.id_cliente == solicitacao.id_cliente)
                    )
                    cliente = result_cliente.scalars().first()
                    
                    if cliente and cliente.id_cliente in websocket.conexoes_ativas:
                        # Tentar enviar novamente
                        websocket_client = websocket.conexoes_ativas[cliente.id_cliente]
                        try:
                            await websocket_client.send_json({
                                "id_cliente": cliente.id_cliente,
                                "data_inicio": str(solicitacao.data_inicio),
                                "data_fim": str(solicitacao.data_fim),
                                "id_solicitacao": solicitacao.id_solicitacao,
                                "retry": True
                            })
                            print(f"�� Retry enviado para solicitação {solicitacao.id_solicitacao}")
                        except Exception as e:
                            print(f"❌ Erro ao enviar retry para solicitação {solicitacao.id_solicitacao}: {e}")
                            # Incrementar contador de tentativas
                            if not hasattr(solicitacao, 'tentativas'):
                                solicitacao.tentativas = 0
                            solicitacao.tentativas += 1
                            
                            if solicitacao.tentativas >= 3:
                                solicitacao.status = "sem_conexao"
                                print(f"❌ Solicitação {solicitacao.id_solicitacao} marcada como 'sem_conexao'")
                            
                            await db.commit()
                    else:
                        # Cliente não conectado, incrementar tentativas
                        if not hasattr(solicitacao, 'tentativas'):
                            solicitacao.tentativas = 0
                        solicitacao.tentativas += 1
                        
                        if solicitacao.tentativas >= 3:
                            solicitacao.status = "sem_conexao"
                            print(f"❌ Solicitação {solicitacao.id_solicitacao} marcada como 'sem_conexao'")
                        
                        await db.commit()
            
        except Exception as e:
            print(f"Erro no sistema de retry: {e}")
        
        await asyncio.sleep(10)  # Aguardar 10 segundos antes da próxima verificação

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Iniciar o sistema de retry quando a aplicação iniciar
    retry_task = asyncio.create_task(tentar_reprocessar_solicitacoes())
    print("🚀 Sistema de retry iniciado")
    
    yield
    
    # Parar o sistema de retry quando a aplicação parar
    retry_task.cancel()
    try:
        await retry_task
    except asyncio.CancelledError:
        pass
    print("🛑 Sistema de retry parado")

app = FastAPI(title="API Portal XML", lifespan=lifespan)

# 🔥 Habilitar CORS para permitir requisições do frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, substitua pelo domínio do frontend ex: ["https://meusite.com"]
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos os métodos HTTP (GET, POST, PUT, DELETE, OPTIONS, etc.)
    allow_headers=["*"],  # Permite todos os cabeçalhos HTTP
)

# Incluir rotas HTTP
app.include_router(auth.router, prefix="/auth", tags=["Autenticação"])

# Incluir rotas WebSocket
app.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])