from datetime import datetime, timezone
from app.db.database import SessionLocal
from app.models.solicitacao import Solicitacao
from app.models.xmls import XML
from sqlalchemy import select, delete

def limpar_dados_expirados():
    db = SessionLocal()
    try:
        agora = datetime.now(timezone.utc)

        # 1️⃣ Buscar os ID das solicitações cujos XMLs expiraram
        solicitacoes_expiradas = db.query(XML.id_solicitacao).filter(XML.expiracao < agora).all()

        # Extrai só os IDs (pode vir como lista de tuplas)
        ids_solicitacoes_expiradas = [row[0] for row in solicitacoes_expiradas if row[0] is not None]

        # 2️⃣ Deletar os XMLs que expiraram
        deletadas_xmls = db.query(XML).filter(XML.expiracao < agora).delete(synchronize_session=False)

        # 3️⃣ Deletar as solicitações que estão relacionadas aos XMLs expirados
        deletadas_solicitacoes = 0
        if ids_solicitacoes_expiradas:
            deletadas_solicitacoes = (
                db.query(Solicitacao)
                .filter(Solicitacao.id_solicitacao.in_(ids_solicitacoes_expiradas))
                .delete(synchronize_session=False)
            )

        db.commit()


    except Exception as e:
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    limpar_dados_expirados()
