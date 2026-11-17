import os

import pymysql

# dati per collegarsi al database (la password si mette nel file .env)
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "10.10.0.10"),
    "user": os.environ.get("DB_USER", "gasparini.fabrizio"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "fgasparini"),
    "cursorclass": pymysql.cursors.DictCursor,
}


def connetti():
    return pymysql.connect(**DB_CONFIG)


def crea_tabella_utenti():
    with connetti() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS utenti (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(30) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    ruolo ENUM('admin', 'utente') NOT NULL DEFAULT 'utente',
                    creato TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
        conn.commit()


# ---------- studenti ----------

def conta_studenti():
    with connetti() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM studenti")
            return cur.fetchone()["n"]


def elenco_classi():
    with connetti() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT classe FROM studenti ORDER BY classe")
            return [riga["classe"] for riga in cur.fetchall()]


def elenco_indirizzi():
    with connetti() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT indirizzo FROM studenti ORDER BY indirizzo")
            return [riga["indirizzo"] for riga in cur.fetchall()]


def cerca_studenti(q="", classe="", indirizzo="", media_min=None):
    # costruisco la WHERE solo con i filtri compilati.
    # i valori vanno sempre come parametri (%s) e mai dentro la stringa: così niente SQL injection
    sql = "SELECT * FROM studenti WHERE 1=1"
    parametri = []

    if q:
        sql += " AND CONCAT(id, ' ', nome, ' ', cognome, ' ', email) LIKE %s"
        parametri.append("%" + q + "%")
    if classe:
        sql += " AND classe = %s"
        parametri.append(classe)
    if indirizzo:
        sql += " AND indirizzo = %s"
        parametri.append(indirizzo)
    if media_min is not None:
        sql += " AND media_voti >= %s"
        parametri.append(media_min)

    sql += " ORDER BY cognome, nome"

    with connetti() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, parametri)
            return cur.fetchall()


def leggi_studente(id_studente):
    with connetti() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM studenti WHERE id = %s", (id_studente,))
            return cur.fetchone()


# ---------- utenti ----------

def crea_utente(username, password_hash, ruolo="utente"):
    with connetti() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO utenti (username, password_hash, ruolo) VALUES (%s, %s, %s)",
                (username, password_hash, ruolo),
            )
            nuovo_id = cur.lastrowid
        conn.commit()
    return nuovo_id


def leggi_utente(id_utente):
    with connetti() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, username, ruolo, creato FROM utenti WHERE id = %s", (id_utente,))
            return cur.fetchone()


def leggi_utente_per_username(username):
    with connetti() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM utenti WHERE username = %s", (username,))
            return cur.fetchone()


def elenco_utenti():
    with connetti() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, username, ruolo, creato FROM utenti ORDER BY ruolo, username")
            return cur.fetchall()


def conta_admin():
    with connetti() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM utenti WHERE ruolo = 'admin'")
            return cur.fetchone()["n"]


def cambia_ruolo(id_utente, ruolo):
    with connetti() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE utenti SET ruolo = %s WHERE id = %s", (ruolo, id_utente))
        conn.commit()


def elimina_utente(id_utente):
    with connetti() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM utenti WHERE id = %s", (id_utente,))
        conn.commit()