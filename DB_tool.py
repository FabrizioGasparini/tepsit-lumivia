"""DB_tool – accesso al database MySQL/MariaDB dell'applicazione.

Tutte le query passano da qui: app2.py importa questo modulo e chiama solo
le sue funzioni, senza scrivere SQL.

Tabelle usate:
  studenti        (esistente)  id, nome, cognome, classe, indirizzo,
                               data_nascita, email, media_voti

PROTEZIONE DA SQL INJECTION
  Ogni valore che arriva dall'utente passa come parametro (%s) a
  cursor.execute(): è il driver a fare l'escape, il valore non diventa mai
  codice SQL. Nelle stringhe SQL vengono inseriti solo nomi di tabelle e
  colonne scritti qui nel codice, mai input dell'utente.

La password del DB NON è scritta nel codice: si legge da DB_PASSWORD
(oppure app2.py la chiede all'avvio). Host, utente e database si possono
cambiare con DB_HOST, DB_PORT, DB_USER, DB_NAME.
"""

import os
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal

import pymysql
import pymysql.cursors

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "10.10.0.10"),
    "port": int(os.environ.get("DB_PORT", "3306")),
    "user": os.environ.get("DB_USER", "gasparini.fabrizio"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "fgasparini"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,  # ogni riga è un dizionario
    "connect_timeout": 5,
}


def imposta_password(password):
    """Imposta la password del DB a runtime (es. chiesta all'avvio)."""
    DB_CONFIG["password"] = password


class ErroreDB(Exception):
    """Errore di accesso al database, con un messaggio leggibile per l'utente."""


# ---------------------------------------------------------------------------
# Connessione e helper
# ---------------------------------------------------------------------------
@contextmanager
def connessione():
    """Apre una connessione; commit se va tutto bene, rollback se c'è un
    errore; la chiude sempre."""
    try:
        conn = pymysql.connect(**DB_CONFIG)
    except pymysql.err.OperationalError as e:
        messaggio = (f"Impossibile connettersi al database {DB_CONFIG['database']} "
                     f"su {DB_CONFIG['host']}: {e.args[-1]}")
        if not DB_CONFIG["password"]:
            messaggio += (" — Password non impostata: definisci la variabile "
                          "d'ambiente DB_PASSWORD prima di avviare l'app.")
        raise ErroreDB(messaggio) from e

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _pulisci(riga):
    """Converte i tipi del DB in tipi semplici per HTML e JSON:
    DATE -> 'YYYY-MM-DD', DATETIME -> 'YYYY-MM-DD HH:MM', DECIMAL -> float."""
    for chiave, valore in riga.items():
        if isinstance(valore, datetime):
            riga[chiave] = valore.strftime("%Y-%m-%d %H:%M")
        elif isinstance(valore, date):
            riga[chiave] = valore.isoformat()
        elif isinstance(valore, Decimal):
            riga[chiave] = float(valore)
    return riga


def _leggi(sql, parametri=()):
    """Esegue una SELECT e restituisce la lista di righe (dizionari)."""
    with connessione() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, parametri)
            return [_pulisci(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Studenti – lettura
# ---------------------------------------------------------------------------
_SELECT_STUDENTI = """
    SELECT s.id, s.nome, s.cognome, s.classe, s.indirizzo, s.data_nascita,
           s.email, s.media_voti
    FROM studenti s
"""


def conta_studenti():
    return _leggi("SELECT COUNT(*) AS n FROM studenti")[0]["n"]


def elenco_classi():
    righe = _leggi("SELECT DISTINCT classe FROM studenti ORDER BY classe")
    return [r["classe"] for r in righe if r["classe"]]


def elenco_indirizzi():
    righe = _leggi("SELECT DISTINCT indirizzo FROM studenti ORDER BY indirizzo")
    return [r["indirizzo"] for r in righe if r["indirizzo"]]


def cerca_studenti(q="", classe="", indirizzo="", media_min=None):
    """Studenti che rispettano TUTTI i filtri non vuoti, ordinati per cognome.
    q cerca in id, nome, cognome ed email."""
    condizioni, parametri = [], []

    if q:
        # escape dei caratteri jolly di LIKE: "%" e "_" si cercano letteralmente
        testo = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        condizioni.append("CONCAT_WS(' ', s.id, s.nome, s.cognome, s.email) LIKE %s")
        parametri.append(f"%{testo}%")
    if classe:
        condizioni.append("s.classe = %s")
        parametri.append(classe)
    if indirizzo:
        condizioni.append("s.indirizzo = %s")
        parametri.append(indirizzo)
    if media_min is not None:
        condizioni.append("s.media_voti >= %s")
        parametri.append(media_min)

    sql = _SELECT_STUDENTI
    if condizioni:
        sql += " WHERE " + " AND ".join(condizioni)
    sql += " ORDER BY s.cognome, s.nome, s.id"

    return _leggi(sql, parametri)


def leggi_studente(id_studente):
    righe = _leggi(_SELECT_STUDENTI + " WHERE s.id = %s", (id_studente,))
    return righe[0] if righe else None


# ---------------------------------------------------------------------------
# Prova veloce: python DB_tool.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not DB_CONFIG["password"]:
        from getpass import getpass
        imposta_password(getpass(f"Password per {DB_CONFIG['user']}@{DB_CONFIG['host']}: "))
    try:
        print(f"Connesso a {DB_CONFIG['database']} su {DB_CONFIG['host']}")
        print("Studenti:", conta_studenti())
        print("Classi:", elenco_classi())
    except ErroreDB as e:
        print("ERRORE:", e)
