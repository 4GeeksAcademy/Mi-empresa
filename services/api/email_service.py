"""Servicio de envío de emails transaccionales usando Resend."""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")


def send_password_reset_email(email: str, token: str) -> None:
    """
    Envía un email con el enlace de restablecimiento de contraseña.

    Si RESEND_API_KEY no está configurada o falla el envío,
    loguea el enlace en consola para desarrollo local.
    """
    reset_url = f"{FRONTEND_URL}/reset-password?token={token}"

    if not RESEND_API_KEY:
        logger.warning(
            "⚠️  RESEND_API_KEY no configurada.\n"
            "📧 Enlace de restablecimiento para %s:\n   %s",
            email,
            reset_url,
        )
        return

    try:
        import httpx

        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": EMAIL_FROM,
                "to": [email],
                "subject": "Restablece tu contraseña - TrackFlow",
                "html": _build_reset_email_html(reset_url),
            },
            timeout=10.0,
        )
        
        if response.status_code == 200:
            logger.info("✅ Email de restablecimiento enviado a %s", email)
        else:
            # Si Resend falla, mostrar el enlace en consola para desarrollo
            logger.warning(
                "⚠️  Resend devolvió %d. Enlace para desarrollo:\n   %s",
                response.status_code,
                reset_url,
            )
            logger.warning("Respuesta de Resend: %s", response.text)
            
    except Exception as exc:
        # Si hay error de red o cualquier otro problema, mostrar el enlace
        logger.warning(
            "⚠️  Error al enviar email (%s). Enlace para desarrollo:\n   %s",
            str(exc),
            reset_url,
        )


def _build_reset_email_html(reset_url: str) -> str:
    """Genera el HTML de laPlantilla del email de restablecimiento."""
    return f"""
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Restablece tu contraseña</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f4f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:480px;margin:40px auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
    <div style="background:#1a1a2e;padding:32px 24px;text-align:center;">
      <h1 style="color:#ffffff;margin:0;font-size:22px;font-weight:700;">TrackFlow</h1>
    </div>
    <div style="padding:32px 24px;">
      <h2 style="color:#1a1a2e;font-size:20px;margin:0 0 16px;">Restablece tu contraseña</h2>
      <p style="color:#52525b;font-size:15px;line-height:1.6;margin:0 0 24px;">
        Hemos recibido una solicitud para restablecer la contraseña de tu cuenta.
        Haz clic en el botón de abajo para elegir una nueva contraseña. Este enlace
        expirará en <strong>30 minutos</strong>.
      </p>
      <div style="text-align:center;margin:0 0 24px;">
        <a href="{reset_url}"
           style="display:inline-block;background:#1a1a2e;color:#ffffff;text-decoration:none;
                  padding:14px 32px;border-radius:8px;font-size:15px;font-weight:600;">
          Restablecer contraseña
        </a>
      </div>
      <p style="color:#a1a1aa;font-size:13px;line-height:1.5;margin:0 0 8px;">
        Si no solicitaste este cambio, puedes ignorar este mensaje.
        Tu contraseña no se modificará a menos que hagas clic en el enlace.
      </p>
      <p style="color:#a1a1aa;font-size:13px;line-height:1.5;margin:0;">
        Si el botón no funciona, copia y pega esta URL en tu navegador:<br>
        <a href="{reset_url}" style="color:#6366f1;word-break:break-all;">{reset_url}</a>
      </p>
    </div>
    <div style="background:#f4f4f5;padding:16px 24px;text-align:center;">
      <p style="color:#a1a1aa;font-size:12px;margin:0;">© TrackFlow · Email transaccional</p>
    </div>
  </div>
</body>
</html>
"""
