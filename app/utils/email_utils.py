import os
import smtplib
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

        print(f"✅ E-mail enviado para {destinatario}")

    except Exception as e:
        print(f"❌ Erro ao enviar e-mail: {str(e)}")
