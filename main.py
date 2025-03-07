from fastapi import FastAPI
from app.routes import auth, websocket

app = FastAPI(title="Minha API FastAPI")

# Incluir rotas HTTP
app.include_router(auth.router, prefix="/auth", tags=["Autenticação"])

# Incluir rotas WebSocket
app.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])
