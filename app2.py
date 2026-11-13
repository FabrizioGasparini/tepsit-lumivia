import hmac
import os
import secrets
import time
from datetime import date
from functools import wraps

# Carica le impostazioni dal file .env (se esiste) PRIMA di importare
# DB_tool e mail_tool, che leggono le variabili d'ambiente all'import.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import (Flask, abort, flash, g, jsonify, redirect,
                   render_template, request, url_for)

import DB_tool
from DB_tool import ErroreDB
from dati_azienda import dati_azienda

app = Flask(__name__)
# chiave per i messaggi flash; se non impostata se ne genera una casuale a ogni avvio
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

TOKEN_DURATA = 3600
token_attivi = {}  # token -> {"id_utente": ..., "scadenza": ...}

TIPI_VALIDI = ("personale", "scolastica", "altro")  # tipi del modulo /form
dati_riepilogo = {}

# Credenziali di prova (dalla versione 5 gli utenti saranno nel database)
USERNAME = "ciccio"
PASSWORD = "pasticcio1"


def confronta(a, b):
    """Confronto a tempo costante: non rivela quanti caratteri sono giusti."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ---------------------------------------------------------------------------
# Token e utente corrente
# ---------------------------------------------------------------------------
def leggi_token():
    """Il token può arrivare dall'header Authorization: Bearer ... oppure dal cookie."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return request.cookies.get("token")


def crea_token(id_utente):
    token = secrets.token_urlsafe(32)
    token_attivi[token] = {"id_utente": id_utente, "scadenza": time.time() + TOKEN_DURATA}
    return token


def revoca_token(token):
    if not token:
        return False
    return token_attivi.pop(token, None) is not None


def id_da_token(token):
    info = token_attivi.get(token) if token else None
    if not info:
        return None
    if time.time() > info["scadenza"]:
        del token_attivi[token]
        return None
    return info["id_utente"]


def utente_attuale():
    """L'utente loggato (dict con id e username) o None."""
    if "utente" not in g:
        g.utente = None
        if id_da_token(leggi_token()):
            g.utente = {"id": 1, "username": USERNAME, "ruolo": "utente"}
    return g.utente


def vuole_json():
    """True se il client è un'API (Bearer o Accept JSON) e non un browser."""
    return (request.headers.get("Authorization", "").startswith("Bearer ")
            or request.accept_mimetypes.best == "application/json")


def login_richiesto(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not utente_attuale():
            if vuole_json():
                return jsonify({"errore": "Non autenticato"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def imposta_cookie(risposta, token):
    risposta.set_cookie("token", token, max_age=TOKEN_DURATA,
                        httponly=True, samesite="Lax")
    return risposta


@app.context_processor
def inietta_utente():
    """Rende disponibile `utente_corrente` in tutti i template."""
    return {"utente_corrente": utente_attuale()}


# ---------------------------------------------------------------------------
# Filtri Jinja
# ---------------------------------------------------------------------------
@app.template_filter("data_it")
def data_it(valore):
    """'2009-03-14' -> '14/03/2009'"""
    try:
        return date.fromisoformat(str(valore)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return valore or ""


@app.template_filter("eta")
def eta(valore):
    try:
        nascita = date.fromisoformat(str(valore)[:10])
    except ValueError:
        return ""
    oggi = date.today()
    return oggi.year - nascita.year - ((oggi.month, oggi.day) < (nascita.month, nascita.day))


# ---------------------------------------------------------------------------
# Errori
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def non_trovato(_):
    if vuole_json():
        return jsonify({"errore": "Non trovato"}), 404
    return render_template("errore.html", codice=404,
                           messaggio="La pagina o lo studente che cerchi non esiste."), 404


@app.errorhandler(ErroreDB)
def database_giu(e):
    if vuole_json():
        return jsonify({"errore": str(e)}), 503
    return render_template("errore.html", codice=503, messaggio=str(e)), 503


# ---------------------------------------------------------------------------
# Login e logout
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET"])
def login():
    if utente_attuale():
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login_post():
    dati = request.get_json(silent=True) or request.form
    username = (dati.get("username") or "").strip()
    password = dati.get("password") or ""

    if not (confronta(username, USERNAME) and confronta(password, PASSWORD)):
        return jsonify({"errore": "Credenziali errate"}), 401

    token = crea_token(1)
    risposta = jsonify({"token": token, "redirect": url_for("dashboard")})
    return imposta_cookie(risposta, token)


@app.route("/logout", methods=["POST"])
@login_richiesto
def logout():
    """Revoca il token lato server e cancella il cookie lato client.
    È POST così un link o un'immagine su un altro sito non può sloggare l'utente."""
    revoca_token(leggi_token())
    if vuole_json():
        risposta = jsonify({"messaggio": "Logout effettuato"})
    else:
        risposta = redirect(url_for("login"), code=303)
    risposta.delete_cookie("token", httponly=True, samesite="Lax")
    return risposta


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def leggi_filtri(args, classi, indirizzi):
    """Legge i filtri dalla query string, scartando i valori non validi.
    Classe e indirizzo sono accettati solo se esistono davvero nel DB."""
    filtri = {
        "q": (args.get("q") or "").strip()[:100],
        "classe": args.get("classe", ""),
        "indirizzo": args.get("indirizzo", ""),
    }
    if filtri["classe"] not in classi:
        filtri["classe"] = ""
    if filtri["indirizzo"] not in indirizzi:
        filtri["indirizzo"] = ""
    for chiave in ("media_min",):
        filtri[chiave] = None
        try:
            valore = float((args.get(chiave) or "").replace(",", "."))
            if 0 <= valore <= 10:
                filtri[chiave] = valore
        except ValueError:
            pass
    return filtri


def studenti_filtrati():
    classi = DB_tool.elenco_classi()
    indirizzi = DB_tool.elenco_indirizzi()
    filtri = leggi_filtri(request.args, classi, indirizzi)
    return filtri, DB_tool.cerca_studenti(**filtri), classi, indirizzi


@app.route("/dashboard", methods=["GET"])
@login_richiesto
def dashboard():
    filtri, righe, classi, indirizzi = studenti_filtrati()
    totale = DB_tool.conta_studenti()

    if vuole_json():
        return jsonify({"filtri": filtri, "totale": totale,
                        "trovati": len(righe), "dati": righe})

    return render_template(
        "dashboard.html",
        righe=righe,
        filtri=filtri,
        totale=totale,
        classi=classi,
        indirizzi=indirizzi,
    )


# ---------------------------------------------------------------------------
# Studenti: scheda
# ---------------------------------------------------------------------------
def leggi_studente_o_404(id_studente):
    studente = DB_tool.leggi_studente(id_studente)
    if not studente:
        abort(404)
    return studente


@app.route("/studenti/<int:id_studente>")
@login_richiesto
def scheda_studente(id_studente):
    studente = leggi_studente_o_404(id_studente)
    if vuole_json():
        return jsonify(studente)
    return render_template("studente.html", s=studente)


# ---------------------------------------------------------------------------
# Pagine già esistenti: azienda e modulo
# ---------------------------------------------------------------------------
@app.route("/azienda", methods=["GET"])
@login_richiesto
def azienda():
    if vuole_json():
        return jsonify(dati_azienda)
    max_fatturato = max(f["milioni"] for f in dati_azienda["fatturato"])
    return render_template("azienda.html", a=dati_azienda,
                           utente=utente_attuale()["username"],
                           max_fatturato=max_fatturato)


@app.route("/form", methods=["GET"])
@login_richiesto
def form():
    return render_template("form.html")


@app.route("/riepilogo", methods=["POST"])
@login_richiesto
def submit():
    nome = request.form.get("nome", "").strip()
    tipo = request.form.get("tipo", "")
    data_inserita = request.form.get("data", "")
    conferma = request.form.get("conferma") == "true"

    if not nome:
        return jsonify({"errore": "Nome obbligatorio"}), 400
    if tipo not in TIPI_VALIDI:
        return jsonify({"errore": "Tipo non valido"}), 400
    try:
        data_valida = date.fromisoformat(data_inserita)
    except (ValueError, TypeError):
        return jsonify({"errore": "Data non valida"}), 400
    if not conferma:
        return jsonify({"errore": "Conferma obbligatoria"}), 400

    dati_riepilogo.clear()
    dati_riepilogo.update({"nome": nome, "tipo": tipo,
                           "data": data_valida.isoformat(), "conferma": conferma})
    return redirect(url_for("mostra_riepilogo"), code=303)


@app.route("/riepilogo", methods=["GET"])
@login_richiesto
def mostra_riepilogo():
    if not dati_riepilogo:
        if vuole_json():
            return jsonify({"errore": "Nessun modulo inviato"}), 400
        flash("Non hai ancora inviato nessuna richiesta.", "errore")
        return redirect(url_for("form"))
    if vuole_json():
        return jsonify({"messaggio": "Modulo compilato correttamente", "dati": dati_riepilogo})
    return render_template("riepilogo.html", dati=dati_riepilogo)


# ---------------------------------------------------------------------------
# Avvio
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from getpass import getpass

    # Se DB_PASSWORD non è impostata la chiedo (il testo digitato non si vede).
    # La salvo anche in os.environ: il reloader di Flask (debug=True) riavvia
    # il programma in un processo figlio, che così la eredita.
    if not DB_tool.DB_CONFIG["password"]:
        pw = getpass(f"Password database per {DB_tool.DB_CONFIG['user']}"
                     f"@{DB_tool.DB_CONFIG['host']}: ")
        os.environ["DB_PASSWORD"] = pw
        DB_tool.imposta_password(pw)

    # Con debug=True Flask riavvia il programma in un processo figlio
    # (WERKZEUG_RUN_MAIN=true): la preparazione la faccio una volta sola.
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        try:
            print(f" * Database {DB_tool.DB_CONFIG['database']} su "
                  f"{DB_tool.DB_CONFIG['host']}: {DB_tool.conta_studenti()} studenti")
        except ErroreDB as e:
            print(f" * ATTENZIONE: {e}\n   L'app mostrerà un errore finché il DB non è raggiungibile.")

    app.run(debug=True, port=5001)
