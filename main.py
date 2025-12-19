from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
from contextlib import asynccontextmanager

# Carregar variáveis de ambiente do .env
load_dotenv()

from app.routes import auth, websocket, feedback, batch, sync
from app.utils.retry_service import retry_service
from app.services.batch_processor import batch_processor

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Iniciar os serviços quando a aplicação iniciar
    await retry_service.start()
    await batch_processor.start()
    
    yield
    
    # Parar os serviços quando a aplicação parar
    await retry_service.stop()
    await batch_processor.stop()

app = FastAPI(
    title="API Portal XML",
    description="API para gerenciamento de XMLs e sincronização de dados",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",  # Documentação Swagger UI
    redoc_url="/redoc",  # Documentação ReDoc
    openapi_url="/openapi.json"  # Esquema OpenAPI JSON
)

# 🔥 Habilitar CORS para permitir requisições do frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, substitua pelo domínio do frontend ex: ["https://meusite.com"]
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos os métodos HTTP (GET, POST, PUT, DELETE, OPTIONS, etc.)
    allow_headers=["*"],  # Permite todos os cabeçalhos HTTP
)

# Incluir rotas HTTP
# Todas as rotas devem ter /api no prefixo
app.include_router(auth.router, prefix="/api/auth", tags=["Autenticação"])
app.include_router(feedback.router, prefix="/api/feedback", tags=["Feedback"])
app.include_router(batch.router, prefix="/api/auth", tags=["Solicitações em Lote"])
app.include_router(sync.router, prefix="/api", tags=["Sincronização"])

# Incluir rotas WebSocket
app.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])

# Expor também endpoint HTTP para clientes conectados em /api/ws/clientes-conectados
app.include_router(websocket.api_router, prefix="/api/ws", tags=["WebSocket"])