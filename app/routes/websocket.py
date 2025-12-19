from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel

# Router principal para rotas sob o prefixo /ws
router = APIRouter()

# Router adicional apenas para expor rotas HTTP sob /api
api_router = APIRouter()

# Dicionário para armazenar conexões ativas
conexoes_ativas = {}


class Mensagem(BaseModel):
    id_cliente: int
    data_inicio: str
    data_fim: str


@router.websocket("/{id_cliente}")
async def websocket_endpoint(websocket: WebSocket, id_cliente: int):
    await websocket.accept()
    conexoes_ativas[id_cliente] = websocket

    try:
        while True:
            message = await websocket.receive_text()
    except WebSocketDisconnect:
        conexoes_ativas.pop(id_cliente, None)


@router.post("/enviar-mensagem")
async def enviar_mensagem(mensagem: Mensagem):
    if mensagem.id_cliente in conexoes_ativas:
        websocket = conexoes_ativas[mensagem.id_cliente]
        await websocket.send_json(mensagem.dict())
        return {"status": "Mensagem enviada"}
    else:
        return {"status": "Cliente não conectado"}


@router.get("/clientes-conectados")
async def listar_clientes_conectados_ws():
    """
    Versão original sob o prefixo /ws (ex: GET /ws/clientes-conectados)
    """
    return {"clientes_conectados": list(conexoes_ativas.keys())} if conexoes_ativas else {
        "mensagem": "Nenhum cliente conectado."
    }


@api_router.get("/clientes-conectados")
async def listar_clientes_conectados_api():
    """
    Versão HTTP sob o prefixo /api (ex: GET /api/clientes-conectados)
    """
    return {"clientes_conectados": list(conexoes_ativas.keys())} if conexoes_ativas else {
        "mensagem": "Nenhum cliente conectado."
    }
