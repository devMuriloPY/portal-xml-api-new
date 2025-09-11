from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
from contextlib import asynccontextmanager

# Carregar variáveis de ambiente do .env
load_dotenv()

from app.routes import auth, websocket, feedback
from app.utils.retry_service import retry_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Iniciar o sistema de retry quando a aplicação iniciar
    await retry_service.start()
    
    yield
    
    # Parar o sistema de retry quando a aplicação parar
    await retry_service.stop()

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
app.include_router(feedback.router, prefix="/feedback", tags=["Feedback"])

# Incluir rotas WebSocket
app.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])