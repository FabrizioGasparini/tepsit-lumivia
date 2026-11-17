import secrets
import time
from datetime import date
from functools import wraps
from getpass import getpass

from dotenv import load_dotenv
load_dotenv()  # legge DB_PASSWORD dal file .env (va fatto prima di importare DB_tool)

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import DB_tool
from dati_azienda import dati_azienda

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

DURATA_SESSIONE = 3600  # 1 ora
sessioni = {}           # token -> {"id_utente": ..., "scadenza": ...}
dati_riepilogo = {}


# ---------- sessioni e permessi ----------

def utente_loggato():
    token = request.cookies.get("token")
    sessione = sessioni.get(token)
    if not sessione:
        return None
    if time.time() > sessione["scadenza"]:
        del sessioni[token]
        return None
    # rileggo l'utente dal db così se cambia ruolo si vede subito
    return DB_tool.leggi_utente(sessione["id_utente"])


def login_richiesto(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not utente_loggato():
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_richiesto(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        utente = utente_loggato()
        if not utente:
            return redirect(url_for("login"))
        if utente["ruolo"] != "admin":
            flash("Questa pagina è solo per i gestori.", "errore")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper


@app.context_processor
def utente_nei_template():
    return {"utente_corrente": utente_loggato()}


@app.template_filter("data_it")
def data_it(data):
    return data.strftime("%d/%m/%Y") if data else ""


@app.template_filter("eta")
def eta(nascita):
    oggi = date.today()
    return oggi.year - nascita.year - ((oggi.month, oggi.day) < (nascita.month, nascita.day))


@app.errorhandler(404)
def non_trovato(e):
    return render_template("errore.html", codice=404, messaggio="La pagina che cerchi non esiste."), 404


def controlla_password(password, conferma):
    errori = []
    if len(password) < 8:
        errori.append("La password deve avere almeno 8 caratteri.")
    if password.isalpha() or password.isdigit():
        errori.append("La password non può essere fatta solo di lettere o solo di numeri.")
    if password != conferma:
        errori.append("Le due password non coincidono.")
    return errori


# ---------- login, registrazione, logout ----------

@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET"])
def login():
    if utente_loggato():
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login_post():
    dati = request.get_json()
    username = dati.get("username", "").strip()
    password = dati.get("password", "")

    utente = DB_tool.leggi_utente_per_username(username)
    if not utente or not check_password_hash(utente["password_hash"], password):
        return jsonify({"errore": "Credenziali errate"}), 401

    token = secrets.token_urlsafe(32)
    sessioni[token] = {"id_utente": utente["id"], "scadenza": time.time() + DURATA_SESSIONE}

    risposta = jsonify({"redirect": url_for("dashboard")})
    risposta.set_cookie("token", token, max_age=DURATA_SESSIONE, httponly=True, samesite="Lax")
    return risposta


@app.route("/registrati", methods=["GET", "POST"])
def registrati():
    if request.method == "GET":
        return render_template("registrati.html", errori=[], username="")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    conferma = request.form.get("conferma", "")

    errori = []
    if len(username) < 3 or len(username) > 30 or " " in username:
        errori.append("Lo username deve avere da 3 a 30 caratteri, senza spazi.")
    elif DB_tool.leggi_utente_per_username(username):
        errori.append("Questo username è già usato.")
    errori += controlla_password(password, conferma)

    if errori:
        return render_template("registrati.html", errori=errori, username=username), 400

    # salvo solo l'hash della password (pbkdf2 + sha256 con salt), mai la password vera
    password_hash = generate_password_hash(password, method="pbkdf2:sha256")
    id_utente = DB_tool.crea_utente(username, password_hash, "utente")

    # dopo la registrazione lo faccio entrare direttamente
    token = secrets.token_urlsafe(32)
    sessioni[token] = {"id_utente": id_utente, "scadenza": time.time() + DURATA_SESSIONE}
    flash(f"Benvenuto {username}!", "ok")
    risposta = redirect(url_for("dashboard"))
    risposta.set_cookie("token", token, max_age=DURATA_SESSIONE, httponly=True, samesite="Lax")
    return risposta


@app.route("/logout", methods=["POST"])
def logout():
    sessioni.pop(request.cookies.get("token"), None)  # il token non vale più
    risposta = redirect(url_for("login"))
    risposta.delete_cookie("token")
    return risposta


# ---------- dashboard studenti ----------

@app.route("/dashboard")
@login_richiesto
def dashboard():
    filtri = {
        "q": request.args.get("q", "").strip(),
        "classe": request.args.get("classe", ""),
        "indirizzo": request.args.get("indirizzo", ""),
        "media_min": None,
    }
    try:
        filtri["media_min"] = float(request.args.get("media_min", "").replace(",", "."))
    except ValueError:
        pass

    return render_template(
        "dashboard.html",
        righe=DB_tool.cerca_studenti(**filtri),
        filtri=filtri,
        totale=DB_tool.conta_studenti(),
        classi=DB_tool.elenco_classi(),
        indirizzi=DB_tool.elenco_indirizzi(),
    )


@app.route("/studenti/<int:id_studente>")
@login_richiesto
def scheda_studente(id_studente):
    studente = DB_tool.leggi_studente(id_studente)
    if not studente:
        abort(404)
    return render_template("studente.html", s=studente)


# ---------- gestione utenti (solo admin) ----------

@app.route("/utenti")
@admin_richiesto
def gestione_utenti():
    return render_template("utenti.html", utenti=DB_tool.elenco_utenti())


@app.route("/utenti/<int:id_utente>/ruolo", methods=["POST"])
@admin_richiesto
def cambia_ruolo(id_utente):
    ruolo = request.form.get("ruolo")
    if id_utente == utente_loggato()["id"]:
        flash("Non puoi cambiare il tuo ruolo.", "errore")
    elif ruolo in ("admin", "utente"):
        DB_tool.cambia_ruolo(id_utente, ruolo)
        flash("Ruolo aggiornato.", "ok")
    return redirect(url_for("gestione_utenti"))


@app.route("/utenti/<int:id_utente>/elimina", methods=["POST"])
@admin_richiesto
def elimina_utente(id_utente):
    if id_utente == utente_loggato()["id"]:
        flash("Non puoi eliminare il tuo account.", "errore")
    else:
        DB_tool.elimina_utente(id_utente)
        # chiudo anche le sue sessioni aperte
        for token in [t for t, s in sessioni.items() if s["id_utente"] == id_utente]:
            del sessioni[token]
        flash("Utente eliminato.", "ok")
    return redirect(url_for("gestione_utenti"))


# ---------- azienda e modulo ----------

@app.route("/azienda")
@login_richiesto
def azienda():
    return render_template("azienda.html", a=dati_azienda)


@app.route("/form")
@login_richiesto
def form():
    return render_template("form.html")


@app.route("/riepilogo", methods=["POST"])
@login_richiesto
def submit():
    nome = request.form.get("nome", "").strip()
    tipo = request.form.get("tipo", "")
    data = request.form.get("data", "")

    if not nome or tipo not in ("personale", "scolastica", "altro") or not data:
        flash("Compila tutti i campi del modulo.", "errore")
        return redirect(url_for("form"))

    dati_riepilogo.update({"nome": nome, "tipo": tipo, "data": date.fromisoformat(data)})
    return redirect(url_for("mostra_riepilogo"))


@app.route("/riepilogo")
@login_richiesto
def mostra_riepilogo():
    if not dati_riepilogo:
        return redirect(url_for("form"))
    return render_template("riepilogo.html", dati=dati_riepilogo)


# ---------- avvio ----------

if __name__ == "__main__":
    if not DB_tool.DB_CONFIG["password"]:
        DB_tool.DB_CONFIG["password"] = getpass("Password del database: ")

    DB_tool.crea_tabella_utenti()

    # la prima volta non ci sono admin: lo creo dal terminale
    if DB_tool.conta_admin() == 0:
        print("Crea il primo utente admin")
        username = input("Username: ").strip()
        password = getpass("Password: ")
        DB_tool.crea_utente(username, generate_password_hash(password, method="pbkdf2:sha256"), "admin")
        print("Admin creato!")

    app.run(debug=True, port=5001, use_reloader=False)