from datetime import datetime, timedelta
from app.db.database import SessionLocal
from app.models.solicitacao import Solicitacao
from app.models.xmls import XML  # se você tiver o model

def limpar_dados_expirados():
    db = SessionLocal()
    try:
        limite = datetime.utcnow() - timedelta(hours=24)

        deletadas_xmls = db.query(XML).filter(XML.data_envio < limite).delete()
        deletadas_solicitacoes = db.query(Solicitacao).filter(Solicitacao.data_solicitacao < limite).delete()

        db.commit()
        print(f"🧼 XMLs apagados: {deletadas_xmls}, Solicitações apagadas: {deletadas_solicitacoes}")
    except Exception as e:
        print(f"❌ Erro ao limpar dados: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    limpar_dados_expirados()
