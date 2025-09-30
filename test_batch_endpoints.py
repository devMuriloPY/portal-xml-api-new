#!/usr/bin/env python3
"""
Script de teste para os endpoints de solicitação em lote
"""

import asyncio
import httpx
import json
from datetime import datetime, date, timedelta

# Configurações
BASE_URL = "http://localhost:8000"
AUTH_ENDPOINT = f"{BASE_URL}/auth/login"
BATCH_ENDPOINT = f"{BASE_URL}/auth/solicitacoes/batch"

# Dados de teste
TEST_CREDENTIALS = {
    "cnpj": "12.345.678/0001-90",  # Substitua por um CNPJ válido do seu banco
    "senha": "senha123"  # Substitua por uma senha válida
}

async def test_batch_endpoints():
    """Testa todos os endpoints de lote"""
    
    async with httpx.AsyncClient() as client:
        print("🚀 Iniciando testes dos endpoints de lote...")
        
        # 1. Fazer login para obter token
        print("\n1. 🔐 Fazendo login...")
        try:
            login_response = await client.post(AUTH_ENDPOINT, json=TEST_CREDENTIALS)
            if login_response.status_code != 200:
                print(f"❌ Erro no login: {login_response.status_code}")
                print(f"Resposta: {login_response.text}")
                return
            
            token = login_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            print("✅ Login realizado com sucesso")
            
        except Exception as e:
            print(f"❌ Erro no login: {e}")
            return
        
        # 2. Listar clientes para obter IDs válidos
        print("\n2. 📋 Listando clientes...")
        try:
            clientes_response = await client.get(f"{BASE_URL}/auth/clientes", headers=headers)
            if clientes_response.status_code != 200:
                print(f"❌ Erro ao listar clientes: {clientes_response.status_code}")
                print(f"Resposta: {clientes_response.text}")
                return
            
            clientes = clientes_response.json()
            if not clientes or isinstance(clientes, dict) and "mensagem" in clientes:
                print("⚠️ Nenhum cliente encontrado. Criando dados de teste...")
                # Usar IDs fictícios para teste
                client_ids = ["1", "2", "3"]
            else:
                client_ids = [str(cliente["id_cliente"]) for cliente in clientes[:3]]
                print(f"✅ Encontrados {len(clientes)} clientes")
            
        except Exception as e:
            print(f"❌ Erro ao listar clientes: {e}")
            client_ids = ["1", "2", "3"]  # Fallback
        
        # 3. Testar criação de lote
        print("\n3. 📦 Criando solicitação em lote...")
        try:
            # Datas de teste (último mês)
            hoje = date.today()
            data_fim = hoje - timedelta(days=1)
            data_inicio = data_fim - timedelta(days=30)
            
            batch_data = {
                "client_ids": client_ids,
                "data_inicio": data_inicio.isoformat(),
                "data_fim": data_fim.isoformat()
            }
            
            print(f"Dados do lote: {json.dumps(batch_data, indent=2)}")
            
            batch_response = await client.post(BATCH_ENDPOINT, json=batch_data, headers=headers)
            print(f"Status: {batch_response.status_code}")
            print(f"Resposta: {json.dumps(batch_response.json(), indent=2, default=str)}")
            
            if batch_response.status_code == 201:
                batch_id = batch_response.json()["batch_id"]
                print(f"✅ Lote criado com sucesso: {batch_id}")
            else:
                print(f"❌ Erro ao criar lote: {batch_response.status_code}")
                return
                
        except Exception as e:
            print(f"❌ Erro ao criar lote: {e}")
            return
        
        # 4. Testar consulta de status do lote
        print(f"\n4. 🔍 Consultando status do lote {batch_id}...")
        try:
            status_response = await client.get(f"{BATCH_ENDPOINT}/{batch_id}", headers=headers)
            print(f"Status: {status_response.status_code}")
            print(f"Resposta: {json.dumps(status_response.json(), indent=2, default=str)}")
            
            if status_response.status_code == 200:
                print("✅ Status do lote consultado com sucesso")
            else:
                print(f"❌ Erro ao consultar status: {status_response.status_code}")
                
        except Exception as e:
            print(f"❌ Erro ao consultar status: {e}")
        
        # 5. Testar listagem de lotes
        print("\n5. 📋 Listando lotes...")
        try:
            list_response = await client.get(f"{BATCH_ENDPOINT}?page=1&limit=10", headers=headers)
            print(f"Status: {list_response.status_code}")
            print(f"Resposta: {json.dumps(list_response.json(), indent=2, default=str)}")
            
            if list_response.status_code == 200:
                print("✅ Lista de lotes obtida com sucesso")
            else:
                print(f"❌ Erro ao listar lotes: {list_response.status_code}")
                
        except Exception as e:
            print(f"❌ Erro ao listar lotes: {e}")
        
        # 6. Testar validações (casos de erro)
        print("\n6. 🧪 Testando validações...")
        
        # Teste 1: Lista vazia de clientes
        print("\n6.1. Testando lista vazia de clientes...")
        try:
            invalid_data = {
                "client_ids": [],
                "data_inicio": data_inicio.isoformat(),
                "data_fim": data_fim.isoformat()
            }
            
            invalid_response = await client.post(BATCH_ENDPOINT, json=invalid_data, headers=headers)
            print(f"Status: {invalid_response.status_code}")
            print(f"Resposta: {json.dumps(invalid_response.json(), indent=2, default=str)}")
            
            if invalid_response.status_code == 422:
                print("✅ Validação de lista vazia funcionando")
            else:
                print("⚠️ Validação de lista vazia não funcionou como esperado")
                
        except Exception as e:
            print(f"❌ Erro no teste de validação: {e}")
        
        # Teste 2: Datas inválidas
        print("\n6.2. Testando datas inválidas...")
        try:
            invalid_data = {
                "client_ids": client_ids[:1],
                "data_inicio": "2024-13-01",  # Mês inválido
                "data_fim": data_fim.isoformat()
            }
            
            invalid_response = await client.post(BATCH_ENDPOINT, json=invalid_data, headers=headers)
            print(f"Status: {invalid_response.status_code}")
            print(f"Resposta: {json.dumps(invalid_response.json(), indent=2, default=str)}")
            
            if invalid_response.status_code == 422:
                print("✅ Validação de datas inválidas funcionando")
            else:
                print("⚠️ Validação de datas inválidas não funcionou como esperado")
                
        except Exception as e:
            print(f"❌ Erro no teste de validação: {e}")
        
        # Teste 3: Período muito longo
        print("\n6.3. Testando período muito longo...")
        try:
            invalid_data = {
                "client_ids": client_ids[:1],
                "data_inicio": "2020-01-01",
                "data_fim": "2024-12-31"  # Mais de 12 meses
            }
            
            invalid_response = await client.post(BATCH_ENDPOINT, json=invalid_data, headers=headers)
            print(f"Status: {invalid_response.status_code}")
            print(f"Resposta: {json.dumps(invalid_response.json(), indent=2, default=str)}")
            
            if invalid_response.status_code == 422:
                print("✅ Validação de período longo funcionando")
            else:
                print("⚠️ Validação de período longo não funcionou como esperado")
                
        except Exception as e:
            print(f"❌ Erro no teste de validação: {e}")
        
        print("\n🎉 Testes concluídos!")

async def test_rate_limiting():
    """Testa rate limiting"""
    print("\n🚦 Testando rate limiting...")
    
    async with httpx.AsyncClient() as client:
        # Fazer login
        login_response = await client.post(AUTH_ENDPOINT, json=TEST_CREDENTIALS)
        if login_response.status_code != 200:
            print("❌ Erro no login para teste de rate limiting")
            return
        
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Tentar criar múltiplos lotes rapidamente
        for i in range(6):  # Mais que o limite de 5
            try:
                batch_data = {
                    "client_ids": ["1"],
                    "data_inicio": "2024-01-01",
                    "data_fim": "2024-01-02"
                }
                
                response = await client.post(BATCH_ENDPOINT, json=batch_data, headers=headers)
                print(f"Tentativa {i+1}: Status {response.status_code}")
                
                if response.status_code == 429:
                    print("✅ Rate limiting funcionando!")
                    break
                    
            except Exception as e:
                print(f"❌ Erro na tentativa {i+1}: {e}")

if __name__ == "__main__":
    print("🧪 Teste dos Endpoints de Solicitação em Lote")
    print("=" * 50)
    
    # Executar testes
    asyncio.run(test_batch_endpoints())
    asyncio.run(test_rate_limiting())
