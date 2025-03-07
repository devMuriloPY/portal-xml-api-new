from fastapi import FastAPI
from app.routes import auth, websocket

app = FastAPI(title="API Portal XML")

# Incluir rotas HTTP
app.include_router(auth.router, prefix="/auth", tags=["Autenticação"])

# Incluir rotas WebSocket
app.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])
