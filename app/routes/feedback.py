from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
import os
from app.utils.email_utils import enviar_email, renderizar_template_email
from app.routes.auth import obter_contador_logado
from app.models.contador import Contador

router = APIRouter()

class FeedbackRequest(BaseModel):
    tipo_feedback: str = Field(..., description="Tipo do feedback (ex: bug, sugestão, elogio, etc.)")
    descricao: str = Field(..., min_length=10, max_length=1000, description="Descrição detalhada do feedback")
    contador_id: Optional[int] = Field(None, description="ID do contador que está enviando o feedback")

class FeedbackResponse(BaseModel):
    success: bool
    message: str

@router.post("/enviar", response_model=FeedbackResponse)
async def enviar_feedback(
    feedback: FeedbackRequest,
    current_user: Contador = Depends(obter_contador_logado)
):
    """
    Endpoint para enviar feedback do contador para o supervisor.
    """
    try:
        # Email do supervisor (deve estar configurado no .env)
        email_supervisor = os.getenv("EMAIL_SUPERVISOR")
        
        if not email_supervisor:
            raise HTTPException(
                status_code=500, 
                detail="Email do supervisor não configurado no sistema"
            )
        
        # Preparar dados para o template do email
        contexto_email = {
            "nome_contador": current_user.nome,
            "email_contador": current_user.email,
            "tipo_feedback": feedback.tipo_feedback,
            "descricao": feedback.descricao,
            "data_envio": os.popen("date /t").read().strip() if os.name == 'nt' else os.popen("date").read().strip()
        }
        
        # Renderizar template do email
        corpo_email = renderizar_template_email("feedback_template.html", contexto_email)
        
        # Assunto do email
        assunto = f"[Portal XML] Feedback - {feedback.tipo_feedback} - {current_user.nome}"
        
        # Enviar email
        enviar_email(email_supervisor, assunto, corpo_email)
        
        return FeedbackResponse(
            success=True,
            message="Feedback enviado com sucesso para o supervisor!"
        )
        
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Erro interno ao enviar feedback: {str(e)}"
        )
