# Sistema de Redefinição de Senha com OTP

Este documento descreve o novo sistema de redefinição de senha implementado com códigos OTP (One-Time Password) de 4 dígitos.

## Visão Geral

O sistema substitui o fluxo anterior de redefinição de senha por links por um sistema mais seguro baseado em códigos OTP enviados por email.

## Funcionalidades

### 🔐 Segurança
- **OTP de 4 dígitos**: Códigos numéricos de 0000-9999
- **TTL de 15 minutos**: Códigos expiram automaticamente
- **Máximo 5 tentativas**: Proteção contra ataques de força bruta
- **Comparação em tempo constante**: Proteção contra timing attacks
- **Single-use tokens**: Tokens de reset não podem ser reutilizados
- **Auditoria completa**: Log de todas as operações

### 📧 Experiência do Usuário
- **Mensagem neutra**: Não revela se a conta existe
- **Email profissional**: Template HTML responsivo
- **Feedback claro**: Instruções detalhadas no email
- **Rate limiting**: Proteção contra spam

## Endpoints da API

### 1. Solicitar OTP
```http
POST /password/otp/request
Content-Type: application/json

{
  "identifier": "usuario@email.com"
}
```

**Resposta:**
```json
{
  "message": "Se existir uma conta, enviamos um código para o e-mail cadastrado."
}
```

**Características:**
- Aceita email ou CNPJ como identificador
- Sempre retorna a mesma mensagem (não revela se conta existe)
- Gera OTP de 4 dígitos com TTL de 15 minutos
- Envia email com template profissional
- Registra auditoria da operação

### 2. Verificar OTP
```http
POST /password/otp/verify
Content-Type: application/json

{
  "identifier": "usuario@email.com",
  "code": "1234"
}
```

**Resposta de Sucesso:**
```json
{
  "status": "ok",
  "reset_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

**Resposta de Erro:**
```json
{
  "status": "error"
}
```

**Características:**
- Verifica código em tempo constante
- Incrementa contador de tentativas
- Bloqueia após 5 tentativas incorretas
- Gera reset_token válido por 10 minutos
- Marca OTP como usado após sucesso

### 3. Redefinir Senha
```http
POST /password/reset
Authorization: Bearer <reset_token>
Content-Type: application/json

{
  "new_password": "nova_senha_segura"
}
```

**Resposta:**
```json
{
  "message": "Senha atualizada."
}
```

**Características:**
- Requer token de autorização no header
- Valida token (expiração, assinatura, tipo)
- Aplica política de senha existente
- Invalida token após uso
- Envia email de confirmação
- Registra auditoria da operação

## Estrutura do Banco de Dados

### Tabela `otps`
```sql
CREATE TABLE otps (
    id_otp SERIAL PRIMARY KEY,
    identifier VARCHAR NOT NULL,        -- email ou CNPJ
    otp_hash VARCHAR NOT NULL,         -- hash SHA256 do código
    attempts INTEGER DEFAULT 0,       -- tentativas realizadas
    max_attempts INTEGER DEFAULT 5,   -- máximo de tentativas
    expires_at TIMESTAMP NOT NULL,     -- data de expiração
    used BOOLEAN DEFAULT FALSE,       -- se foi usado
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Tabela `audit_logs`
```sql
CREATE TABLE audit_logs (
    id_audit SERIAL PRIMARY KEY,
    user_id INTEGER,                  -- ID do usuário (pode ser null)
    identifier VARCHAR,               -- email ou CNPJ usado
    action VARCHAR NOT NULL,          -- tipo de ação
    ip_address VARCHAR,               -- IP do usuário
    result VARCHAR NOT NULL,          -- resultado da operação
    details TEXT,                     -- detalhes adicionais
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Migração

Para aplicar as mudanças no banco de dados:

```bash
python migration_otp.py
```

## Template de Email

O sistema usa o template `app/utils/otp_template.html` que inclui:
- Design responsivo e profissional
- Código OTP destacado visualmente
- Instruções de segurança
- Informações sobre expiração e tentativas
- Avisos de segurança

## Auditoria

Todas as operações são registradas na tabela `audit_logs` com:
- **otp_request**: Solicitação de OTP
- **otp_verify**: Verificação de código
- **password_reset**: Redefinição de senha

Cada log inclui:
- ID do usuário (quando disponível)
- Identificador usado (email/CNPJ)
- Endereço IP
- Resultado da operação
- Detalhes adicionais

## Segurança

### Proteções Implementadas
1. **Timing Attack Protection**: Comparação em tempo constante
2. **Rate Limiting**: Máximo de tentativas por OTP
3. **TTL**: Expiração automática de códigos
4. **Single-use**: Tokens não podem ser reutilizados
5. **Auditoria**: Log completo de operações
6. **Mensagem Neutra**: Não revela existência de contas

### Boas Práticas
- Códigos OTP são gerados com `secrets.randbelow()`
- Hashes são armazenados com SHA256
- Tokens JWT incluem tipo e ID do OTP
- IPs são registrados para auditoria
- Emails são enviados apenas para contas existentes

## Compatibilidade

O novo sistema é totalmente compatível com:
- Sistema de autenticação existente
- Templates de email existentes
- Políticas de senha atuais
- Sistema de auditoria

## Endpoints Removidos

Os seguintes endpoints foram removidos:
- `POST /solicitar-redefinicao`
- `POST /redefinir-senha`

Estes foram substituídos pelos novos endpoints OTP conforme especificado.
