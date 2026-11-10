"""mail_tool – invio delle email dell'applicazione (conferma account, reset password).

Come DB_tool.py per il database, questo modulo è l'unico punto che parla con
il server di posta: app2.py chiama solo invia_conferma() e invia_reset().

CONFIGURAZIONE (variabili d'ambiente)
  SMTP_HOST      es. smtp.gmail.com
  SMTP_PORT      587 (STARTTLS, default) oppure 465 (SSL)
  SMTP_USER      es. tuo.indirizzo@gmail.com
  SMTP_PASSWORD  per Gmail: una "password per le app", NON la password normale
  SMTP_FROM      mittente mostrato (default: SMTP_USER)
  SMTP_SICUREZZA starttls (default), ssl (default se porta 465) oppure nessuna

MODALITÀ SVILUPPO
  Se SMTP_HOST non è impostato, le email NON vengono spedite: vengono
  stampate nel terminale e salvate come file .html nella cartella
  email_inviate/, così si può provare tutto anche senza un server di posta.
"""

import os
import smtplib
import socket
import ssl
from datetime import datetime
from email.message import EmailMessage
from html import escape
from pathlib import Path

CARTELLA_SVILUPPO = Path(__file__).parent / "email_inviate"
NOME_APP = "Lumivia"


def _pulisci_host(valore):
    """Corregge gli errori di battitura più comuni nel .env:
    spazi, virgolette, "https://" davanti, ":587" attaccato in fondo."""
    host = (valore or "").strip().strip("\"'").strip()
    for prefisso in ("https://", "http://", "smtp://"):
        if host.lower().startswith(prefisso):
            host = host[len(prefisso):]
    return host.split("/")[0].split(":")[0]


def configurazione():
    return {
        "host": _pulisci_host(os.environ.get("SMTP_HOST", "")),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "mittente": os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER", ""),
        "sicurezza": os.environ.get("SMTP_SICUREZZA", "").lower()
                     or ("ssl" if os.environ.get("SMTP_PORT") == "465" else "starttls"),
    }


def modalita_sviluppo():
    """True se non c'è un server SMTP configurato."""
    return not configurazione()["host"]


class ErroreMail(Exception):
    """Invio non riuscito, con un messaggio leggibile."""


# ---------------------------------------------------------------------------
# Modello grafico delle email
# ---------------------------------------------------------------------------
def _html(titolo, saluto, testo, bottone, link, nota):
    """HTML con stili inline (molti client di posta ignorano i fogli di stile)."""
    return f"""<!DOCTYPE html>
<html lang="it"><body style="margin:0;padding:32px 16px;background:#f4f4f8;font-family:Arial,Helvetica,sans-serif;color:#18181b">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
           style="max-width:520px;background:#ffffff;border-radius:20px;overflow:hidden">
      <tr><td style="padding:28px 32px;background:linear-gradient(135deg,#667eea,#764ba2);background-color:#6b5fc7">
        <span style="font-size:22px;font-weight:bold;color:#ffffff">{NOME_APP}</span>
      </td></tr>
      <tr><td style="padding:32px">
        <h1 style="margin:0 0 16px;font-size:22px;color:#4c3d99">{escape(titolo)}</h1>
        <p style="margin:0 0 12px;font-size:15px;line-height:1.6">{escape(saluto)}</p>
        <p style="margin:0 0 24px;font-size:15px;line-height:1.6">{escape(testo)}</p>
        <p style="margin:0 0 24px">
          <a href="{escape(link)}" style="display:inline-block;padding:14px 24px;border-radius:12px;
             background-color:#6b5fc7;color:#ffffff;font-weight:bold;text-decoration:none">{escape(bottone)}</a>
        </p>
        <p style="margin:0 0 8px;font-size:13px;color:#71717a">Se il bottone non funziona, copia questo indirizzo nel browser:</p>
        <p style="margin:0 0 24px;font-size:13px;word-break:break-all"><a href="{escape(link)}" style="color:#667eea">{escape(link)}</a></p>
        <p style="margin:0;font-size:13px;color:#71717a">{escape(nota)}</p>
      </td></tr>
    </table>
  </td></tr></table>
</body></html>"""


def _testo(saluto, testo, link, nota):
    """Versione solo testo, per i client che non mostrano l'HTML."""
    return f"{saluto}\n\n{testo}\n\n{link}\n\n{nota}\n\n— {NOME_APP}"


# ---------------------------------------------------------------------------
# Invio
# ---------------------------------------------------------------------------
def invia(destinatario, oggetto, testo, html):
    cfg = configurazione()

    if modalita_sviluppo():
        CARTELLA_SVILUPPO.mkdir(exist_ok=True)
        nome = datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".html"
        (CARTELLA_SVILUPPO / nome).write_text(html, encoding="utf-8")
        print("\n" + "=" * 70)
        print(f" EMAIL (modalità sviluppo, non spedita) → {destinatario}")
        print(f" Oggetto: {oggetto}\n")
        print(testo)
        print(f"\n Salvata in: {CARTELLA_SVILUPPO / nome}")
        print("=" * 70 + "\n")
        return

    msg = EmailMessage()
    msg["Subject"] = oggetto
    msg["From"] = f"{NOME_APP} <{cfg['mittente']}>"
    msg["To"] = destinatario
    msg.set_content(testo)
    msg.add_alternative(html, subtype="html")

    try:
        contesto = ssl.create_default_context()
        if cfg["sicurezza"] == "ssl":
            server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=contesto, timeout=15)
        else:
            server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=15)
            if cfg["sicurezza"] == "starttls":
                server.starttls(context=contesto)
        with server:
            if cfg["user"]:
                server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
    except socket.gaierror as e:
        raise ErroreMail(
            f"Server di posta «{cfg['host']}» non trovato: controlla SMTP_HOST nel file .env "
            f"(per Gmail è smtp.gmail.com) e che il PC sia connesso a internet."
        ) from e
    except smtplib.SMTPAuthenticationError as e:
        raise ErroreMail(
            f"Login SMTP rifiutato per «{cfg['user']}»: per Gmail serve una "
            f"'password per le app' di 16 lettere, non la password normale."
        ) from e
    except (smtplib.SMTPException, OSError) as e:
        raise ErroreMail(f"Invio email non riuscito tramite {cfg['host']}:{cfg['port']}: {e}") from e


def invia_conferma(destinatario, username, link, ore_validita):
    saluto = f"Ciao {username},"
    testo = ("grazie per esserti registrato. Per attivare il tuo account "
             "conferma il tuo indirizzo email cliccando il bottone qui sotto.")
    nota = (f"Il link scade tra {ore_validita} ore. Se non sei stato tu a "
            "registrarti, ignora questa email: l'account resterà disattivato.")
    invia(destinatario, f"Conferma il tuo account {NOME_APP}",
          _testo(saluto, testo, link, nota),
          _html("Conferma il tuo indirizzo email", saluto, testo, "Attiva il mio account", link, nota))


def invia_reset(destinatario, username, link, minuti_validita):
    saluto = f"Ciao {username},"
    testo = ("abbiamo ricevuto una richiesta di reimpostazione della password. "
             "Clicca il bottone qui sotto per sceglierne una nuova.")
    nota = (f"Il link scade tra {minuti_validita} minuti e funziona una sola volta. "
            "Se non hai chiesto tu il reset, ignora questa email: la password resta quella di prima.")
    invia(destinatario, f"Reimposta la password {NOME_APP}",
          _testo(saluto, testo, link, nota),
          _html("Reimposta la password", saluto, testo, "Scegli una nuova password", link, nota))


# ---------------------------------------------------------------------------
# Prova veloce: python mail_tool.py indirizzo@esempio.it
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Uso: python mail_tool.py indirizzo@destinatario.it")
        sys.exit(1)
    print("Modalità:", "sviluppo (nessun invio reale)" if modalita_sviluppo()
          else f"SMTP {configurazione()['host']}:{configurazione()['port']}")
    try:
        invia_conferma(sys.argv[1], "prova", "http://localhost:5001/conferma/esempio", 24)
        print("Fatto.")
    except ErroreMail as e:
        print("ERRORE:", e)
