from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ValidationError
import re

class BatchValidationError(Exception):
    def __init__(self, message: str, details: Dict[str, Any] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

class BatchValidator:
    @staticmethod
    def validate_client_ids(client_ids: List[str]) -> None:
        """Valida lista de IDs de clientes"""
        if not client_ids:
            raise BatchValidationError(
                "Lista de clientes não pode estar vazia",
                {"client_ids": ["Lista de clientes é obrigatória"]}
            )
        
        if len(client_ids) > 50:
            raise BatchValidationError(
                "Máximo de 50 clientes por lote",
                {"client_ids": [f"Máximo permitido: 50, recebido: {len(client_ids)}"]}
            )
        
        # Validar formato dos IDs
        invalid_ids = []
        for client_id in client_ids:
            if not client_id or not client_id.strip():
                invalid_ids.append("ID vazio")
            elif not re.match(r'^\d+$', str(client_id)):
                invalid_ids.append(f"ID inválido: {client_id}")
        
        if invalid_ids:
            raise BatchValidationError(
                "IDs de clientes inválidos",
                {"client_ids": invalid_ids}
            )
    
    @staticmethod
    def validate_dates(data_inicio: str, data_fim: str) -> tuple[date, date]:
        """Valida e converte datas"""
        try:
            inicio = datetime.strptime(data_inicio, "%Y-%m-%d").date()
        except ValueError:
            raise BatchValidationError(
                "Data de início inválida",
                {"data_inicio": ["Formato deve ser YYYY-MM-DD"]}
            )
        
        try:
            fim = datetime.strptime(data_fim, "%Y-%m-%d").date()
        except ValueError:
            raise BatchValidationError(
                "Data de fim inválida",
                {"data_fim": ["Formato deve ser YYYY-MM-DD"]}
            )
        
        # Validar ordem das datas
        if inicio > fim:
            raise BatchValidationError(
                "Data de início deve ser menor ou igual à data de fim",
                {
                    "data_inicio": ["Data de início deve ser anterior à data de fim"],
                    "data_fim": ["Data de fim deve ser posterior à data de início"]
                }
            )
        
        # Validar período máximo (12 meses)
        diff = fim - inicio
        if diff.days > 365:
            raise BatchValidationError(
                "Período máximo permitido é de 12 meses",
                {
                    "data_inicio": ["Período muito longo"],
                    "data_fim": ["Período muito longo"]
                }
            )
        
        # Validar se as datas não são muito antigas (máximo 2 anos atrás)
        two_years_ago = date.today() - timedelta(days=730)
        if inicio < two_years_ago:
            raise BatchValidationError(
                "Data de início muito antiga",
                {"data_inicio": ["Data deve ser posterior a 2 anos atrás"]}
            )
        
        # Validar se as datas não são futuras
        if fim > date.today():
            raise BatchValidationError(
                "Data de fim não pode ser futura",
                {"data_fim": ["Data de fim deve ser anterior ou igual a hoje"]}
            )
        
        return inicio, fim
    
    @staticmethod
    def validate_batch_request(data: Dict[str, Any]) -> Dict[str, Any]:
        """Valida uma requisição de lote completa"""
        errors = {}
        
        # Validar client_ids
        if "client_ids" not in data:
            errors["client_ids"] = ["Campo obrigatório"]
        else:
            try:
                BatchValidator.validate_client_ids(data["client_ids"])
            except BatchValidationError as e:
                errors.update(e.details)
        
        # Validar datas
        if "data_inicio" not in data:
            errors["data_inicio"] = ["Campo obrigatório"]
        if "data_fim" not in data:
            errors["data_fim"] = ["Campo obrigatório"]
        
        if "data_inicio" in data and "data_fim" in data:
            try:
                BatchValidator.validate_dates(data["data_inicio"], data["data_fim"])
            except BatchValidationError as e:
                errors.update(e.details)
        
        if errors:
            raise BatchValidationError("Dados inválidos", errors)
        
        return data
    
    @staticmethod
    def validate_pagination_params(page: int, limit: int) -> tuple[int, int]:
        """Valida parâmetros de paginação"""
        if page < 1:
            page = 1
        
        if limit < 1:
            limit = 10
        elif limit > 100:
            limit = 100
        
        return page, limit
    
    @staticmethod
    def validate_status_filter(status: str) -> str:
        """Valida filtro de status"""
        valid_statuses = ["pending", "processing", "completed", "error", "all"]
        
        if status not in valid_statuses:
            raise BatchValidationError(
                "Status inválido",
                {"status": [f"Valores válidos: {', '.join(valid_statuses)}"]}
            )
        
        return status

class BatchRequestSchema(BaseModel):
    """Schema para validação de requisição de lote"""
    client_ids: List[str]
    data_inicio: str
    data_fim: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "client_ids": ["1", "2", "3"],
                "data_inicio": "2024-01-01",
                "data_fim": "2024-01-31"
            }
        }
    
    @classmethod
    def validate_and_convert(cls, data: Dict[str, Any]) -> "BatchRequestSchema":
        """Valida e converte dados para o schema"""
        try:
            # Validar usando o validator
            BatchValidator.validate_batch_request(data)
            
            # Converter datas
            data_inicio, data_fim = BatchValidator.validate_dates(
                data["data_inicio"], 
                data["data_fim"]
            )
            
            return cls(
                client_ids=data["client_ids"],
                data_inicio=data_inicio.isoformat(),
                data_fim=data_fim.isoformat()
            )
        except BatchValidationError as e:
            raise ValidationError.from_exception_data(
                "BatchRequestSchema",
                e.details
            )
