from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, websocket
from dotenv import load_dotenv
load_dotenv()
app = FastAPI(title="API Portal XML")

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
