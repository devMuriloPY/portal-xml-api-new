import os
import smtplib
from jinja2 import Environment, FileSystemLoader
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def enviar_email(destinatario: str, assunto: str, corpo: str):
    remetente = os.getenv("EMAIL_SENDER")
    senha = os.getenv("EMAIL_PASSWORD")
    servidor_smtp = os.getenv("EMAIL_SMTP", "smtp.gmail.com")
    porta_smtp = int(os.getenv("EMAIL_PORT", 587))

    if not remetente or not senha:
        raise ValueError("As credenciais de e-mail não foram configuradas corretamente.")

    try:
        msg = MIMEMultipart()
        msg["From"] = remetente
        msg["To"] = destinatario
        msg["Subject"] = assunto
        msg.attach(MIMEText(corpo, "html"))

        with smtplib.SMTP(servidor_smtp, porta_smtp) as server:
            server.starttls()
            server.login(remetente, senha)
            server.sendmail(remetente, destinatario, msg.as_string())


    except Exception as e:
        raise  # Re-raise the exception to maintain error handling


def renderizar_template_email(nome_arquivo: str, contexto: dict) -> str:
    # Caminho da pasta onde está este arquivo (utils/)
    diretorio = os.path.dirname(__file__)
    
    # Configura o Jinja para carregar os templates do mesmo diretório
    env = Environment(loader=FileSystemLoader(diretorio))
    
    # Carrega e renderiza o template
    template = env.get_template(nome_arquivo)
    return template.render(contexto)