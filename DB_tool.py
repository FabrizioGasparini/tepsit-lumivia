"""DB_tool – accesso al database MySQL/MariaDB dell'applicazione.

Tutte le query passano da qui: app2.py importa questo modulo e chiama solo
le sue funzioni, senza scrivere SQL.

Tabelle usate:
  studenti        (esistente)  id, nome, cognome, classe, indirizzo,
                               data_nascita, email, media_voti
  utenti          (creata da crea_tabelle)  account con password hashata,
                                            ruolo e stato di attivazione
  token_email     (creata da crea_tabelle)  link di conferma / reset password
  foto_studenti   (creata da crea_tabelle)  immagini salvate come BLOB
  log_attivita    (creata da crea_tabelle)  chi ha fatto cosa e quando

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

RUOLI = ("admin", "utente")

# colonne di `studenti` modificabili dall'admin (id escluso)
CAMPI_STUDENTE = ("nome", "cognome", "classe", "indirizzo",
                  "data_nascita", "email", "media_voti")


def imposta_password(password):
    """Imposta la password del DB a runtime (es. chiesta all'avvio)."""
    DB_CONFIG["password"] = password


class ErroreDB(Exception):
    """Errore di accesso al database, con un messaggio leggibile per l'utente."""


class UsernameGiaUsato(Exception):
    """Registrazione con uno username che esiste già."""


class EmailGiaUsata(Exception):
    """Registrazione con un'email che esiste già."""


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


def _scrivi(sql, parametri=()):
    """Esegue INSERT/UPDATE/DELETE. Restituisce (righe_toccate, ultimo_id)."""
    with connessione() as conn:
        with conn.cursor() as cur:
            n = cur.execute(sql, parametri)
            return n, cur.lastrowid


# ---------------------------------------------------------------------------
# Struttura
# ---------------------------------------------------------------------------
def _colonna_esiste(cur, tabella, colonna):
    cur.execute(
        """SELECT 1 FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s""",
        (tabella, colonna),
    )
    return cur.fetchone() is not None


def crea_tabelle():
    """Crea le tabelle dell'applicazione se non esistono (utenti, token_email,
    foto_studenti, log_attivita). Non tocca la tabella `studenti`.
    Si può chiamare a ogni avvio: non cancella né duplica nulla.

    Se `utenti` esiste già da una versione precedente senza le colonne
    `email` e `attivo`, le aggiunge (gli utenti già presenti restano attivi)."""
    with connessione() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS utenti (
                    id            INT AUTO_INCREMENT PRIMARY KEY,
                    username      VARCHAR(30)  NOT NULL UNIQUE,
                    email         VARCHAR(100) NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    ruolo         ENUM('admin', 'utente') NOT NULL DEFAULT 'utente',
                    attivo        TINYINT(1) NOT NULL DEFAULT 0,
                    creato        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # migrazione dalla versione precedente
            if not _colonna_esiste(cur, "utenti", "email"):
                cur.execute("ALTER TABLE utenti ADD COLUMN email VARCHAR(100) NULL UNIQUE AFTER username")
            if not _colonna_esiste(cur, "utenti", "attivo"):
                cur.execute("ALTER TABLE utenti ADD COLUMN attivo TINYINT(1) NOT NULL DEFAULT 0 AFTER ruolo")
                cur.execute("UPDATE utenti SET attivo = 1")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS token_email (
                    token_hash CHAR(64) PRIMARY KEY,
                    utente_id  INT NOT NULL,
                    tipo       ENUM('attivazione', 'reset') NOT NULL,
                    scadenza   DATETIME NOT NULL,
                    creato     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_utente (utente_id, tipo)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS foto_studenti (
                    studente_id INT PRIMARY KEY,
                    dati        MEDIUMBLOB  NOT NULL,
                    mime        VARCHAR(50) NOT NULL,
                    dimensione  INT         NOT NULL,
                    caricata    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS log_attivita (
                    id        INT AUTO_INCREMENT PRIMARY KEY,
                    utente_id INT NULL,
                    username  VARCHAR(30) NULL,
                    azione    VARCHAR(30) NOT NULL,
                    dettaglio VARCHAR(255) NOT NULL DEFAULT '',
                    quando    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_quando (quando)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)


# ---------------------------------------------------------------------------
# Utenti
# ---------------------------------------------------------------------------
_COLONNE_UTENTE = "id, username, email, ruolo, attivo, creato"


def _bool_attivo(riga):
    if riga is not None:
        riga["attivo"] = bool(riga["attivo"])
    return riga


def crea_utente(username, password_hash, ruolo="utente", email=None, attivo=False):
    """Inserisce un utente. La password deve arrivare GIÀ hashata.
    Solleva UsernameGiaUsato o EmailGiaUsata se sono già registrati."""
    if ruolo not in RUOLI:
        raise ValueError(f"Ruolo non valido: {ruolo}")
    try:
        _, nuovo_id = _scrivi(
            """INSERT INTO utenti (username, email, password_hash, ruolo, attivo)
               VALUES (%s, %s, %s, %s, %s)""",
            (username, email, password_hash, ruolo, int(attivo)),
        )
        return nuovo_id
    except pymysql.err.IntegrityError as e:
        # il messaggio di MySQL contiene il nome dell'indice violato
        if "email" in str(e.args[-1]):
            raise EmailGiaUsata(email) from e
        raise UsernameGiaUsato(username) from e


def leggi_utente_per_username(username):
    """Utente con hash della password (serve per il login), oppure None."""
    righe = _leggi(
        f"SELECT {_COLONNE_UTENTE}, password_hash FROM utenti WHERE username = %s",
        (username,),
    )
    return _bool_attivo(righe[0]) if righe else None


def leggi_utente_per_email(email):
    righe = _leggi(f"SELECT {_COLONNE_UTENTE} FROM utenti WHERE email = %s", (email,))
    return _bool_attivo(righe[0]) if righe else None


def leggi_utente(id_utente):
    """Utente senza hash della password, oppure None."""
    righe = _leggi(f"SELECT {_COLONNE_UTENTE} FROM utenti WHERE id = %s", (id_utente,))
    return _bool_attivo(righe[0]) if righe else None


def elenco_utenti():
    righe = _leggi(f"SELECT {_COLONNE_UTENTE} FROM utenti ORDER BY attivo, ruolo, username")
    return [_bool_attivo(r) for r in righe]


def conta_admin():
    return _leggi("SELECT COUNT(*) AS n FROM utenti WHERE ruolo = 'admin'")[0]["n"]


def cambia_ruolo(id_utente, ruolo):
    if ruolo not in RUOLI:
        raise ValueError(f"Ruolo non valido: {ruolo}")
    n, _ = _scrivi("UPDATE utenti SET ruolo = %s WHERE id = %s", (ruolo, id_utente))
    return n > 0


def attiva_utente(id_utente):
    n, _ = _scrivi("UPDATE utenti SET attivo = 1 WHERE id = %s", (id_utente,))
    return n > 0


def aggiorna_password(id_utente, password_hash):
    n, _ = _scrivi("UPDATE utenti SET password_hash = %s WHERE id = %s",
                   (password_hash, id_utente))
    return n > 0


def elimina_utente(id_utente):
    with connessione() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM token_email WHERE utente_id = %s", (id_utente,))
            n = cur.execute("DELETE FROM utenti WHERE id = %s", (id_utente,))
    return n > 0


# ---------------------------------------------------------------------------
# Token inviati per email (attivazione account e reset password)
# ---------------------------------------------------------------------------
# Nel DB si salva solo l'hash SHA-256 del token, mai il token in chiaro: chi
# leggesse la tabella non potrebbe usare i link. Il token vero esiste solo
# nell'email.

def salva_token_email(utente_id, tipo, token_hash, minuti_validita):
    """Salva un nuovo token, cancellando quelli precedenti dello stesso tipo
    (vale sempre e solo l'ultimo link inviato)."""
    with connessione() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM token_email WHERE utente_id = %s AND tipo = %s",
                        (utente_id, tipo))
            cur.execute(
                """INSERT INTO token_email (token_hash, utente_id, tipo, scadenza)
                   VALUES (%s, %s, %s, NOW() + INTERVAL %s MINUTE)""",
                (token_hash, utente_id, tipo, minuti_validita),
            )


def utente_da_token(token_hash, tipo, consuma=True):
    """Restituisce l'id utente se il token esiste, è del tipo giusto e non è
    scaduto, altrimenti None. Con consuma=True il token viene cancellato
    (un link si può usare una volta sola)."""
    with connessione() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT utente_id, scadenza > NOW() AS valido FROM token_email
                   WHERE token_hash = %s AND tipo = %s FOR UPDATE""",
                (token_hash, tipo),
            )
            riga = cur.fetchone()
            if not riga:
                return None
            if consuma or not riga["valido"]:
                cur.execute("DELETE FROM token_email WHERE token_hash = %s", (token_hash,))
            return riga["utente_id"] if riga["valido"] else None


def secondi_da_ultimo_token(utente_id, tipo):
    """Da quanti secondi è stato creato l'ultimo token (None se non ce ne sono).
    Serve a non far partire decine di email di fila."""
    righe = _leggi(
        """SELECT TIMESTAMPDIFF(SECOND, MAX(creato), NOW()) AS s FROM token_email
           WHERE utente_id = %s AND tipo = %s""",
        (utente_id, tipo),
    )
    return righe[0]["s"]


# ---------------------------------------------------------------------------
# Registro attività
# ---------------------------------------------------------------------------
def registra_attivita(utente, azione, dettaglio=""):
    """Annota un'operazione. `utente` è il dict dell'utente (o None)."""
    _scrivi(
        "INSERT INTO log_attivita (utente_id, username, azione, dettaglio) VALUES (%s, %s, %s, %s)",
        (utente["id"] if utente else None, utente["username"] if utente else None,
         azione, dettaglio[:255]),
    )


def ultime_attivita(limite=40):
    return _leggi(
        "SELECT username, azione, dettaglio, quando FROM log_attivita ORDER BY id DESC LIMIT %s",
        (limite,),
    )


def conta_foto():
    return _leggi("SELECT COUNT(*) AS n FROM foto_studenti")[0]["n"]


# ---------------------------------------------------------------------------
# Studenti – lettura
# ---------------------------------------------------------------------------
_SELECT_STUDENTI = """
    SELECT s.id, s.nome, s.cognome, s.classe, s.indirizzo, s.data_nascita,
           s.email, s.media_voti, (f.studente_id IS NOT NULL) AS ha_foto
    FROM studenti s
    LEFT JOIN foto_studenti f ON f.studente_id = s.id
"""


def conta_studenti():
    return _leggi("SELECT COUNT(*) AS n FROM studenti")[0]["n"]


def elenco_classi():
    righe = _leggi("SELECT DISTINCT classe FROM studenti ORDER BY classe")
    return [r["classe"] for r in righe if r["classe"]]


def elenco_indirizzi():
    righe = _leggi("SELECT DISTINCT indirizzo FROM studenti ORDER BY indirizzo")
    return [r["indirizzo"] for r in righe if r["indirizzo"]]


def cerca_studenti(q="", classe="", indirizzo="", media_min=None, media_max=None):
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
    if media_max is not None:
        condizioni.append("s.media_voti < %s")   # escluso: "da 6 a 7" non comprende il 7
        parametri.append(media_max)

    sql = _SELECT_STUDENTI
    if condizioni:
        sql += " WHERE " + " AND ".join(condizioni)
    sql += " ORDER BY s.cognome, s.nome, s.id"

    righe = _leggi(sql, parametri)
    for r in righe:
        r["ha_foto"] = bool(r["ha_foto"])
    return righe


def leggi_studente(id_studente):
    righe = _leggi(_SELECT_STUDENTI + " WHERE s.id = %s", (id_studente,))
    if not righe:
        return None
    righe[0]["ha_foto"] = bool(righe[0]["ha_foto"])
    return righe[0]


def statistiche():
    """Numeri per le card della dashboard."""
    with connessione() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS totale,
                       AVG(media_voti) AS media,
                       COUNT(DISTINCT classe) AS classi,
                       SUM(media_voti >= 8) AS eccellenti,
                       SUM(media_voti < 6) AS fascia_insuff,
                       SUM(media_voti >= 6 AND media_voti < 7) AS fascia_6,
                       SUM(media_voti >= 7 AND media_voti < 8) AS fascia_7,
                       SUM(media_voti >= 8) AS fascia_8
                FROM studenti
            """)
            dati = _pulisci(cur.fetchone())
            cur.execute("""
                SELECT nome, cognome, media_voti FROM studenti
                WHERE media_voti IS NOT NULL
                ORDER BY media_voti DESC, cognome LIMIT 1
            """)
            migliore = cur.fetchone()
    dati["migliore"] = _pulisci(migliore) if migliore else None
    for chiave in ("eccellenti", "fascia_insuff", "fascia_6", "fascia_7", "fascia_8"):
        dati[chiave] = int(dati[chiave] or 0)
    # distribuzione delle medie per la barra della dashboard
    dati["fasce"] = [
        {"etichetta": "Sotto il 6", "da": None, "a": 6, "n": dati["fascia_insuff"], "tono": "insuff"},
        {"etichetta": "Da 6 a 7", "da": 6, "a": 7, "n": dati["fascia_6"], "tono": "sei"},
        {"etichetta": "Da 7 a 8", "da": 7, "a": 8, "n": dati["fascia_7"], "tono": "sette"},
        {"etichetta": "8 e oltre", "da": 8, "a": None, "n": dati["fascia_8"], "tono": "otto"},
    ]
    return dati


# ---------------------------------------------------------------------------
# Studenti – scrittura (solo admin, i controlli di permesso sono in app2.py)
# ---------------------------------------------------------------------------
def crea_studente(dati):
    """Inserisce uno studente. `dati` contiene le chiavi di CAMPI_STUDENTE."""
    colonne = ", ".join(CAMPI_STUDENTE)
    segnaposto = ", ".join(["%s"] * len(CAMPI_STUDENTE))
    _, nuovo_id = _scrivi(
        f"INSERT INTO studenti ({colonne}) VALUES ({segnaposto})",
        [dati[c] for c in CAMPI_STUDENTE],
    )
    return nuovo_id


def aggiorna_studente(id_studente, dati):
    assegnazioni = ", ".join(f"{c} = %s" for c in CAMPI_STUDENTE)
    with connessione() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM studenti WHERE id = %s", (id_studente,))
            if not cur.fetchone():
                return False
            cur.execute(
                f"UPDATE studenti SET {assegnazioni} WHERE id = %s",
                [dati[c] for c in CAMPI_STUDENTE] + [id_studente],
            )
    return True


def elimina_studente(id_studente):
    """Elimina lo studente e la sua foto nella stessa transazione."""
    with connessione() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM foto_studenti WHERE studente_id = %s", (id_studente,))
            n = cur.execute("DELETE FROM studenti WHERE id = %s", (id_studente,))
    return n > 0


# ---------------------------------------------------------------------------
# Foto (immagini salvate nel database come BLOB)
# ---------------------------------------------------------------------------
def salva_foto(id_studente, dati, mime):
    """Salva o sostituisce la foto di uno studente."""
    _scrivi(
        """INSERT INTO foto_studenti (studente_id, dati, mime, dimensione)
           VALUES (%s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE dati = VALUES(dati), mime = VALUES(mime),
                                   dimensione = VALUES(dimensione)""",
        (id_studente, dati, mime, len(dati)),
    )


def leggi_foto(id_studente):
    """Restituisce (bytes, mime, data_caricamento) oppure None."""
    righe = _leggi(
        "SELECT dati, mime, caricata FROM foto_studenti WHERE studente_id = %s",
        (id_studente,),
    )
    if not righe:
        return None
    return righe[0]["dati"], righe[0]["mime"], righe[0]["caricata"]


def elimina_foto(id_studente):
    n, _ = _scrivi("DELETE FROM foto_studenti WHERE studente_id = %s", (id_studente,))
    return n > 0


# ---------------------------------------------------------------------------
# Prova veloce: python DB_tool.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not DB_CONFIG["password"]:
        from getpass import getpass
        imposta_password(getpass(f"Password per {DB_CONFIG['user']}@{DB_CONFIG['host']}: "))
    try:
        crea_tabelle()
        print(f"Connesso a {DB_CONFIG['database']} su {DB_CONFIG['host']}")
        print("Studenti:", conta_studenti(), "| Utenti:", len(elenco_utenti()),
              "| Admin:", conta_admin())
        print("Classi:", elenco_classi())
        print("Statistiche:", statistiche())
    except ErroreDB as e:
        print("ERRORE:", e)
