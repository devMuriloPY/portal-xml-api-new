from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, timedelta
from typing import Dict, List
import asyncio

class RateLimiter:
    def __init__(self):
        # Em produção, usar Redis ou banco de dados
        self.requests: Dict[str, List[datetime]] = {}
        self.cleanup_interval = 300  # 5 minutos
        self.last_cleanup = datetime.now()
    
    def is_allowed(self, key: str, limit: int, window: int) -> bool:
        """Verifica se a requisição está dentro do limite"""
        now = datetime.now()
        
        # Limpeza periódica
        if (now - self.last_cleanup).total_seconds() > self.cleanup_interval:
            self._cleanup_old_requests()
            self.last_cleanup = now
        
        # Obter requisições do usuário
        if key not in self.requests:
            self.requests[key] = []
        
        user_requests = self.requests[key]
        
        # Remover requisições antigas
        cutoff = now - timedelta(seconds=window)
        user_requests[:] = [req_time for req_time in user_requests if req_time > cutoff]
        
        # Verificar limite
        if len(user_requests) >= limit:
            return False
        
        # Adicionar nova requisição
        user_requests.append(now)
        return True
    
    def _cleanup_old_requests(self):
        """Remove requisições antigas de todos os usuários"""
        now = datetime.now()
        cutoff = now - timedelta(hours=1)  # Manter apenas 1 hora
        
        for key in list(self.requests.keys()):
            self.requests[key] = [req_time for req_time in self.requests[key] if req_time > cutoff]
            if not self.requests[key]:
                del self.requests[key]

# Instância global
rate_limiter = RateLimiter()

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, calls: int = 100, period: int = 3600):
        super().__init__(app)
        self.calls = calls
        self.period = period
    
    async def dispatch(self, request: Request, call_next):
        # Aplicar rate limiting apenas para endpoints de lote
        if request.url.path.startswith("/auth/solicitacoes/batch"):
            # Obter identificador do usuário
            user_id = self._get_user_identifier(request)
            
            if user_id:
                if not rate_limiter.is_allowed(f"batch_{user_id}", self.calls, self.period):
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": "rate_limit_exceeded",
                            "message": "Muitas solicitações em lote. Aguarde antes de criar um novo lote."
                        }
                    )
        
        response = await call_next(request)
        return response
    
    def _get_user_identifier(self, request: Request) -> str:
        """Extrai identificador do usuário da requisição"""
        # Tentar obter do token JWT
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            # Em produção, decodificar o JWT para obter o user_id
            # Por simplicidade, usar o IP como fallback
            return request.client.host if request.client else "unknown"
        
        # Fallback para IP
        return request.client.host if request.client else "unknown"
