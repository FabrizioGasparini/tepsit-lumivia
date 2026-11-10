import csv
import hashlib
import io
import os
import re
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

from flask import (Flask, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, url_for)
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash

import DB_tool
import mail_tool
from DB_tool import EmailGiaUsata, ErroreDB, UsernameGiaUsato
from dati_azienda import dati_azienda
from mail_tool import ErroreMail

app = Flask(__name__)
# chiave per i messaggi flash; se non impostata se ne genera una casuale a ogni avvio
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # upload massimo: 5 MB

TOKEN_DURATA = 3600
token_attivi = {}  # token -> {"id_utente": ..., "scadenza": ...}

TIPI_VALIDI = ("personale", "scolastica", "altro")  # tipi del modulo /form
dati_riepilogo = {}

# ---------------------------------------------------------------------------
# Password
# ---------------------------------------------------------------------------
# PBKDF2-SHA256 con 600.000 iterazioni e un "salt" casuale diverso per ogni
# utente. È più sicuro di un semplice md5/sha256: due utenti con la stessa
# password hanno hash diversi e provare password a forza bruta è molto lento.
# Nel DB finisce una stringa tipo "pbkdf2:sha256:600000$<salt>$<hash>".
HASH_METODO = "pbkdf2:sha256:600000"

# hash di una password a caso: al login con uno username inesistente si
# controlla comunque questo, così la risposta impiega lo stesso tempo e non
# rivela quali username esistono
HASH_FINTO = generate_password_hash(secrets.token_hex(16), method=HASH_METODO)


def hash_password(password):
    return generate_password_hash(password, method=HASH_METODO)


def errori_password(password, conferma):
    errori = []
    if len(password) < 8:
        errori.append("La password deve avere almeno 8 caratteri.")
    if len(password) > 128:
        errori.append("La password può avere al massimo 128 caratteri.")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        errori.append("La password deve contenere almeno una lettera e un numero.")
    if password != conferma:
        errori.append("Le due password non coincidono.")
    return errori


USERNAME_RE = re.compile(r"[A-Za-z0-9._-]{3,30}")
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

# ---------------------------------------------------------------------------
# Link via email (conferma account e reset password)
# ---------------------------------------------------------------------------
ORE_VALIDITA_CONFERMA = 24
MINUTI_VALIDITA_RESET = 60
SECONDI_TRA_EMAIL = 60  # attesa minima prima di poter richiedere un'altra email


def hash_token(token):
    """Nel DB salviamo solo l'hash SHA-256 del token, mai il token stesso."""
    return hashlib.sha256(token.encode()).hexdigest()


def link_esterno(endpoint, **parametri):
    """URL completo da mettere nelle email. Se l'app è raggiungibile da un
    indirizzo diverso da quello della richiesta (es. dietro un proxy),
    impostare BASE_URL, ad esempio http://10.10.1.32:5001"""
    base = os.environ.get("BASE_URL", "").rstrip("/")
    if base:
        return base + url_for(endpoint, **parametri)
    return url_for(endpoint, _external=True, **parametri)


def invia_link_conferma(utente):
    token = secrets.token_urlsafe(32)
    DB_tool.salva_token_email(utente["id"], "attivazione", hash_token(token),
                              ORE_VALIDITA_CONFERMA * 60)
    mail_tool.invia_conferma(utente["email"], utente["username"],
                             link_esterno("conferma_account", token=token),
                             ORE_VALIDITA_CONFERMA)


def invia_link_reset(utente):
    token = secrets.token_urlsafe(32)
    DB_tool.salva_token_email(utente["id"], "reset", hash_token(token),
                              MINUTI_VALIDITA_RESET)
    mail_tool.invia_reset(utente["email"], utente["username"],
                          link_esterno("reimposta_password", token=token),
                          MINUTI_VALIDITA_RESET)


def troppo_presto(utente, tipo):
    secondi = DB_tool.secondi_da_ultimo_token(utente["id"], tipo)
    return secondi is not None and secondi < SECONDI_TRA_EMAIL


def registra(azione, dettaglio="", utente=None):
    """Scrive nel registro attività senza mai bloccare l'operazione principale."""
    try:
        DB_tool.registra_attivita(utente or utente_attuale(), azione, dettaglio)
    except Exception:
        app.logger.exception("Registro attività non disponibile")

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
    """L'utente loggato (dict con id, username, ruolo) o None.

    Il ruolo viene riletto dal DB a ogni richiesta: se un admin cambia il
    ruolo di qualcuno o lo elimina, l'effetto è immediato."""
    if "utente" not in g:
        g.utente = None
        token = leggi_token()
        id_utente = id_da_token(token)
        if id_utente:
            try:
                g.utente = DB_tool.leggi_utente(id_utente)
            except ErroreDB:
                g.utente = None
            if g.utente is None or not g.utente["attivo"]:
                revoca_token(token)  # utente eliminato o disattivato: il token non vale più
                g.utente = None
    return g.utente


def revoca_sessioni_utente(id_utente):
    """Chiude tutte le sessioni aperte di un utente (es. dopo il reset password)."""
    for token in [t for t, i in token_attivi.items() if i["id_utente"] == id_utente]:
        revoca_token(token)


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


def admin_richiesto(f):
    """Come login_richiesto, ma in più l'utente deve avere ruolo admin."""
    @wraps(f)
    @login_richiesto
    def wrapper(*args, **kwargs):
        if utente_attuale()["ruolo"] != "admin":
            if vuole_json():
                return jsonify({"errore": "Serve il ruolo admin"}), 403
            flash("Questa operazione è riservata agli amministratori.", "errore")
            return redirect(url_for("dashboard"))
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


@app.errorhandler(413)
def file_troppo_grande(_):
    flash("Il file è troppo grande: massimo 5 MB.", "errore")
    return redirect(request.path)


@app.errorhandler(ErroreDB)
def database_giu(e):
    if vuole_json():
        return jsonify({"errore": str(e)}), 503
    return render_template("errore.html", codice=503, messaggio=str(e)), 503


# ---------------------------------------------------------------------------
# Login, registrazione, logout
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

    try:
        utente = DB_tool.leggi_utente_per_username(username) if username else None
    except ErroreDB as e:
        return jsonify({"errore": str(e)}), 503

    hash_salvato = utente["password_hash"] if utente else HASH_FINTO
    if not (check_password_hash(hash_salvato, password) and utente):
        return jsonify({"errore": "Credenziali errate"}), 401

    # la password è giusta, ma l'email non è ancora stata confermata
    if not utente["attivo"]:
        return jsonify({
            "errore": "Account non ancora attivato: apri il link nell'email di conferma.",
            "reinvia": url_for("reinvia_conferma"),
        }), 403

    token = crea_token(utente["id"])
    risposta = jsonify({"token": token, "ruolo": utente["ruolo"],
                        "redirect": url_for("dashboard")})
    return imposta_cookie(risposta, token)


@app.route("/registrati", methods=["GET", "POST"])
def registrati():
    if utente_attuale():
        return redirect(url_for("dashboard"))
    if request.method == "GET":
        return render_template("registrati.html", errori=[], username="", email="")

    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    conferma = request.form.get("conferma") or ""

    errori = []
    if not USERNAME_RE.fullmatch(username):
        errori.append("Lo username deve avere 3–30 caratteri tra lettere, numeri, punto, trattino e underscore.")
    if not EMAIL_RE.fullmatch(email) or len(email) > 100:
        errori.append("Inserisci un indirizzo email valido.")
    errori += errori_password(password, conferma)

    if not errori:
        try:
            # i nuovi utenti sono sempre "utente" e NON attivi:
            # si attivano dal link nell'email, solo un admin può promuoverli
            id_utente = DB_tool.crea_utente(username, hash_password(password), "utente",
                                            email=email, attivo=False)
        except UsernameGiaUsato:
            errori.append("Questo username è già in uso.")
        except EmailGiaUsata:
            errori.append("Esiste già un account con questa email.")

    if not errori:
        nuovo = DB_tool.leggi_utente(id_utente)
        try:
            invia_link_conferma(nuovo)
        except ErroreMail:
            app.logger.exception("Invio email di conferma fallito")
            # senza email l'account non si potrebbe attivare: lo annullo
            DB_tool.elimina_utente(id_utente)
            errori.append("Non è stato possibile inviare l'email di conferma. Riprova tra poco.")

    if errori:
        return render_template("registrati.html", errori=errori,
                               username=username, email=email), 400

    registra("registrazione", f"nuovo account in attesa di conferma: {email}", utente=nuovo)
    return render_template("messaggio.html", simbolo="busta",
                           titolo="Controlla la tua email",
                           testo=f"Ti abbiamo inviato un link a {email}. Aprilo entro "
                                 f"{ORE_VALIDITA_CONFERMA} ore per attivare l'account.",
                           sviluppo=mail_tool.modalita_sviluppo())


@app.route("/conferma/<token>")
def conferma_account(token):
    id_utente = DB_tool.utente_da_token(hash_token(token), "attivazione")
    if not id_utente:
        return render_template("messaggio.html", simbolo="attenzione", titolo="Link non valido",
                               testo="Il link di conferma è scaduto oppure è già stato usato. "
                                     "Puoi richiederne uno nuovo.",
                               azione=(url_for("reinvia_conferma"), "Invia un nuovo link")), 400

    DB_tool.attiva_utente(id_utente)
    utente = DB_tool.leggi_utente(id_utente)
    registra("conferma email", "account attivato", utente=utente)
    flash(f"Account di {utente['username']} attivato! Ora puoi accedere.", "ok")
    return redirect(url_for("login"), code=303)


def pagina_richiesta_email(tipo, errori=(), email=""):
    """Form con un solo campo email, usato per reinvio conferma e password dimenticata."""
    testi = {
        "conferma": ("Non hai ricevuto l'email?",
                     "Inserisci l'indirizzo con cui ti sei registrato: ti invieremo un nuovo link di attivazione.",
                     "Invia di nuovo il link"),
        "reset": ("Password dimenticata",
                  "Inserisci l'email del tuo account: ti invieremo un link per sceglierne una nuova.",
                  "Invia il link"),
    }
    titolo, testo, bottone = testi[tipo]
    return render_template("richiesta_email.html", titolo=titolo, testo=testo,
                           bottone=bottone, errori=list(errori), email=email,
                           azione=request.path)


def risposta_email_inviata(email):
    # stessa risposta che l'account esista o no: non riveliamo quali email sono registrate
    return render_template("messaggio.html", simbolo="busta", titolo="Controlla la tua email",
                           testo=f"Se esiste un account collegato a {email}, riceverai "
                                 "a breve un'email con le istruzioni.",
                           sviluppo=mail_tool.modalita_sviluppo())


@app.route("/reinvia-conferma", methods=["GET", "POST"])
def reinvia_conferma():
    if request.method == "GET":
        return pagina_richiesta_email("conferma")

    email = (request.form.get("email") or "").strip().lower()
    if not EMAIL_RE.fullmatch(email):
        return pagina_richiesta_email("conferma", ["Inserisci un indirizzo email valido."], email), 400

    utente = DB_tool.leggi_utente_per_email(email)
    if utente and not utente["attivo"]:
        if troppo_presto(utente, "attivazione"):
            return pagina_richiesta_email(
                "conferma", [f"Ti abbiamo appena inviato un'email: aspetta {SECONDI_TRA_EMAIL} secondi prima di richiederne un'altra."],
                email), 429
        try:
            invia_link_conferma(utente)
        except ErroreMail:
            app.logger.exception("Reinvio conferma fallito")
    return risposta_email_inviata(email)


@app.route("/password-dimenticata", methods=["GET", "POST"])
def password_dimenticata():
    if request.method == "GET":
        return pagina_richiesta_email("reset")

    email = (request.form.get("email") or "").strip().lower()
    if not EMAIL_RE.fullmatch(email):
        return pagina_richiesta_email("reset", ["Inserisci un indirizzo email valido."], email), 400

    utente = DB_tool.leggi_utente_per_email(email)
    if utente and utente["attivo"] and not troppo_presto(utente, "reset"):
        try:
            invia_link_reset(utente)
            registra("richiesta reset", "inviato link per nuova password", utente=utente)
        except ErroreMail:
            app.logger.exception("Invio reset fallito")
    return risposta_email_inviata(email)


@app.route("/reimposta-password/<token>", methods=["GET", "POST"])
def reimposta_password(token):
    def link_scaduto():
        return render_template(
            "messaggio.html", simbolo="attenzione", titolo="Link non valido",
            testo="Il link per reimpostare la password è scaduto oppure è già stato usato.",
            azione=(url_for("password_dimenticata"), "Richiedi un nuovo link"))

    if request.method == "GET":
        # controllo il token senza consumarlo: verrà usato al salvataggio
        if not DB_tool.utente_da_token(hash_token(token), "reset", consuma=False):
            return link_scaduto(), 400
        return render_template("reimposta_password.html", errori=[])

    password = request.form.get("password") or ""
    errori = errori_password(password, request.form.get("conferma") or "")
    if errori:
        return render_template("reimposta_password.html", errori=errori), 400

    id_utente = DB_tool.utente_da_token(hash_token(token), "reset")
    if not id_utente:
        return link_scaduto(), 400

    DB_tool.aggiorna_password(id_utente, hash_password(password))
    revoca_sessioni_utente(id_utente)  # chi aveva rubato la sessione viene buttato fuori
    registra("reset password", "password cambiata dal link email",
             utente=DB_tool.leggi_utente(id_utente))
    flash("Password aggiornata. Ora puoi accedere con quella nuova.", "ok")
    return redirect(url_for("login"), code=303)


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
    for chiave in ("media_min", "media_max"):
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
    stats = DB_tool.statistiche()

    if vuole_json():
        return jsonify({"filtri": filtri, "totale": stats["totale"],
                        "trovati": len(righe), "dati": righe})

    return render_template(
        "dashboard.html",
        righe=righe,
        filtri=filtri,
        totale=stats["totale"],
        stats=stats,
        classi=classi,
        indirizzi=indirizzi,
        query_attuale=request.query_string.decode(),
    )


@app.route("/dashboard/export.csv", methods=["GET"])
@login_richiesto
def esporta_csv():
    """Scarica in CSV gli studenti che corrispondono ai filtri attuali."""
    _, righe, _, _ = studenti_filtrati()

    buffer = io.StringIO()
    buffer.write("﻿")  # BOM: Excel riconosce gli accenti
    scrittore = csv.writer(buffer, delimiter=";")  # ; per Excel in italiano
    scrittore.writerow(["ID", "Cognome", "Nome", "Classe", "Indirizzo",
                        "Data di nascita", "Email", "Media"])
    for s in righe:
        media = "" if s["media_voti"] is None else f"{s['media_voti']:.2f}".replace(".", ",")
        scrittore.writerow([s["id"], s["cognome"], s["nome"], s["classe"], s["indirizzo"],
                            data_it(s["data_nascita"]), s["email"], media])

    return Response(buffer.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=studenti.csv"})


# ---------------------------------------------------------------------------
# Studenti: scheda, foto e CRUD (scrittura solo admin)
# ---------------------------------------------------------------------------
Image.MAX_IMAGE_PIXELS = 40_000_000  # rifiuta immagini enormi ("decompression bomb")
FORMATI_IMMAGINE = {"JPEG", "PNG", "WEBP", "GIF"}
LATO_MAX_FOTO = 600


def elabora_foto(file):
    """Controlla che il file sia davvero un'immagine e la converte in un JPEG
    di massimo 600x600 px. Restituisce i byte da salvare nel DB, None se non
    è stato caricato nulla, oppure solleva ValueError.

    Ricodificare l'immagine con Pillow elimina anche eventuali dati estranei
    nascosti nel file e i metadati EXIF (posizione GPS ecc.)."""
    if not file or not file.filename:
        return None
    try:
        img = Image.open(file.stream)
        if img.format not in FORMATI_IMMAGINE:
            raise ValueError("Formato non supportato: usa JPG, PNG, WEBP o GIF.")
        img.verify()                 # controlla l'integrità del file
        file.stream.seek(0)
        img = Image.open(file.stream)  # dopo verify() va riaperta
        img = ImageOps.exif_transpose(img)  # raddrizza le foto da smartphone
        if img.mode in ("RGBA", "LA", "P"):
            # il JPEG non ha trasparenza: metto le parti trasparenti su sfondo bianco
            img = img.convert("RGBA")
            sfondo = Image.new("RGB", img.size, "white")
            sfondo.paste(img, mask=img.getchannel("A"))
            img = sfondo
        img = img.convert("RGB")
        img.thumbnail((LATO_MAX_FOTO, LATO_MAX_FOTO))
        uscita = io.BytesIO()
        img.save(uscita, "JPEG", quality=85, optimize=True)
        return uscita.getvalue()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise ValueError("Il file caricato non è un'immagine valida.")


CLASSE_RE = re.compile(r"[1-5][A-Z]{1,3}")


def valida_studente(form):
    """Restituisce (dati_puliti, valori_grezzi, errori)."""
    grezzi = {c: (form.get(c) or "").strip() for c in DB_tool.CAMPI_STUDENTE}
    grezzi["classe"] = grezzi["classe"].upper()
    errori = []

    for campo, etichetta in (("nome", "Il nome"), ("cognome", "Il cognome"),
                             ("indirizzo", "L'indirizzo")):
        if not grezzi[campo]:
            errori.append(f"{etichetta} è obbligatorio.")
        elif len(grezzi[campo]) > 50:
            errori.append(f"{etichetta} può avere al massimo 50 caratteri.")

    if not CLASSE_RE.fullmatch(grezzi["classe"]):
        errori.append("La classe deve essere tipo 3A, 4B, 5AI…")

    data_nascita = None
    try:
        data_nascita = date.fromisoformat(grezzi["data_nascita"])
        if not (date(1950, 1, 1) <= data_nascita <= date.today()):
            errori.append("La data di nascita non è plausibile.")
    except ValueError:
        errori.append("La data di nascita non è valida.")

    if not EMAIL_RE.fullmatch(grezzi["email"]) or len(grezzi["email"]) > 100:
        errori.append("L'email non è valida.")

    media = None
    if grezzi["media_voti"]:
        try:
            media = round(float(grezzi["media_voti"].replace(",", ".")), 2)
            if not 0 <= media <= 10:
                raise ValueError
        except ValueError:
            errori.append("La media deve essere un numero tra 0 e 10.")

    dati = dict(grezzi, data_nascita=data_nascita, media_voti=media)
    return dati, grezzi, errori


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


@app.route("/studenti/<int:id_studente>/foto")
@login_richiesto
def foto_studente(id_studente):
    """Legge l'immagine dal DB e la restituisce al browser."""
    foto = DB_tool.leggi_foto(id_studente)
    if not foto:
        abort(404)
    dati, mime, _ = foto
    return Response(dati, mimetype=mime,
                    headers={"Cache-Control": "private, max-age=60",
                             "X-Content-Type-Options": "nosniff"})


def salva_studente(studente=None):
    """Logica comune a "nuovo" e "modifica"."""
    dati, grezzi, errori = valida_studente(request.form)

    foto = None
    try:
        foto = elabora_foto(request.files.get("foto"))
    except ValueError as e:
        errori.append(str(e))

    if not errori:
        try:
            if studente:
                id_studente = studente["id"]
                DB_tool.aggiorna_studente(id_studente, dati)
            else:
                id_studente = DB_tool.crea_studente(dati)

            if foto:
                DB_tool.salva_foto(id_studente, foto, "image/jpeg")
            elif studente and request.form.get("rimuovi_foto"):
                DB_tool.elimina_foto(id_studente)
        except DB_tool.pymysql.MySQLError as e:
            errori.append(f"Il database ha rifiutato i dati: {e.args[-1]}")

    if errori:
        return render_template("studente_form.html", studente=studente, valori=grezzi,
                               errori=errori, indirizzi=DB_tool.elenco_indirizzi()), 400

    nome = f"{dati['nome']} {dati['cognome']}"
    dettaglio = f"#{id_studente} {nome}"
    if foto:
        dettaglio += " (nuova foto)"
    elif studente and request.form.get("rimuovi_foto"):
        dettaglio += " (foto rimossa)"
    registra("modifica studente" if studente else "nuovo studente", dettaglio)
    flash(f"{nome} {'aggiornato' if studente else 'aggiunto'} correttamente.", "ok")
    return redirect(url_for("scheda_studente", id_studente=id_studente), code=303)


@app.route("/studenti/nuovo", methods=["GET", "POST"])
@admin_richiesto
def nuovo_studente():
    if request.method == "POST":
        return salva_studente()
    return render_template("studente_form.html", studente=None, valori={}, errori=[],
                           indirizzi=DB_tool.elenco_indirizzi())


@app.route("/studenti/<int:id_studente>/modifica", methods=["GET", "POST"])
@admin_richiesto
def modifica_studente(id_studente):
    studente = leggi_studente_o_404(id_studente)
    if request.method == "POST":
        return salva_studente(studente)
    valori = {c: ("" if studente[c] is None else str(studente[c]))
              for c in DB_tool.CAMPI_STUDENTE}
    return render_template("studente_form.html", studente=studente, valori=valori,
                           errori=[], indirizzi=DB_tool.elenco_indirizzi())


@app.route("/studenti/<int:id_studente>/elimina", methods=["POST"])
@admin_richiesto
def elimina_studente(id_studente):
    studente = leggi_studente_o_404(id_studente)
    DB_tool.elimina_studente(id_studente)
    registra("elimina studente", f"#{id_studente} {studente['nome']} {studente['cognome']}")
    if vuole_json():
        return jsonify({"messaggio": "Studente eliminato"})
    flash(f"{studente['nome']} {studente['cognome']} è stato eliminato.", "ok")
    return redirect(url_for("dashboard"), code=303)


# ---------------------------------------------------------------------------
# Area gestori (solo admin): pannello e gestione utenti
# ---------------------------------------------------------------------------
@app.route("/gestione")
@admin_richiesto
def pannello_gestione():
    """Endpoint riservato ai gestori: panoramica, account da attivare e
    registro di tutte le operazioni fatte nell'applicazione."""
    utenti = DB_tool.elenco_utenti()
    dati = {
        "studenti": DB_tool.conta_studenti(),
        "foto": DB_tool.conta_foto(),
        "utenti_attivi": sum(u["attivo"] for u in utenti),
        "admin": sum(u["ruolo"] == "admin" for u in utenti),
        "in_attesa": [u for u in utenti if not u["attivo"]],
        "attivita": DB_tool.ultime_attivita(),
        "smtp": "sviluppo (email nel terminale)" if mail_tool.modalita_sviluppo()
                else mail_tool.configurazione()["host"],
    }
    if vuole_json():
        return jsonify(dati)
    return render_template("gestione.html", **dati)


def torna_indietro():
    """Dopo un'azione sugli utenti torno alla pagina da cui è partita
    (pannello o elenco utenti). Accetto solo questi due endpoint."""
    destinazione = request.form.get("torna")
    if destinazione not in ("pannello_gestione", "gestione_utenti"):
        destinazione = "gestione_utenti"
    return redirect(url_for(destinazione), code=303)


@app.route("/utenti")
@admin_richiesto
def gestione_utenti():
    utenti = DB_tool.elenco_utenti()
    if vuole_json():
        return jsonify(utenti)
    return render_template("utenti.html", utenti=utenti)


@app.route("/utenti/<int:id_utente>/ruolo", methods=["POST"])
@admin_richiesto
def cambia_ruolo(id_utente):
    ruolo = request.form.get("ruolo", "")
    bersaglio = DB_tool.leggi_utente(id_utente)
    if not bersaglio:
        abort(404)
    if id_utente == utente_attuale()["id"]:
        flash("Non puoi cambiare il tuo stesso ruolo.", "errore")
    elif ruolo not in DB_tool.RUOLI:
        flash("Ruolo non valido.", "errore")
    elif ruolo != bersaglio["ruolo"]:
        DB_tool.cambia_ruolo(id_utente, ruolo)
        registra("cambio ruolo", f"{bersaglio['username']}: {bersaglio['ruolo']} → {ruolo}")
        flash(f"{bersaglio['username']} ora è «{ruolo}».", "ok")
    return torna_indietro()


@app.route("/utenti/<int:id_utente>/attiva", methods=["POST"])
@admin_richiesto
def attiva_utente(id_utente):
    """Attivazione manuale da parte di un gestore (es. email mai arrivata)."""
    bersaglio = DB_tool.leggi_utente(id_utente)
    if not bersaglio:
        abort(404)
    if not bersaglio["attivo"]:
        DB_tool.attiva_utente(id_utente)
        registra("attivazione manuale", bersaglio["username"])
        flash(f"Account di {bersaglio['username']} attivato.", "ok")
    return torna_indietro()


@app.route("/utenti/<int:id_utente>/elimina", methods=["POST"])
@admin_richiesto
def elimina_utente(id_utente):
    bersaglio = DB_tool.leggi_utente(id_utente)
    if not bersaglio:
        abort(404)
    if id_utente == utente_attuale()["id"]:
        flash("Non puoi eliminare il tuo stesso account.", "errore")
    else:
        DB_tool.elimina_utente(id_utente)
        revoca_sessioni_utente(id_utente)  # lo butto fuori subito
        registra("elimina utente", bersaglio["username"])
        flash(f"Account di {bersaglio['username']} eliminato.", "ok")
    return torna_indietro()


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
def crea_primo_admin():
    """Se nel DB non c'è nessun admin, lo crea: dalle variabili ADMIN_USERNAME
    e ADMIN_PASSWORD se impostate, altrimenti chiedendo i dati nel terminale."""
    from getpass import getpass

    print("\n * Nessun amministratore nel database: creiamo il primo.")
    username = os.environ.get("ADMIN_USERNAME") or input("   Username admin: ").strip()
    password = os.environ.get("ADMIN_PASSWORD")
    while True:
        if not USERNAME_RE.fullmatch(username):
            username = input("   Username non valido (3–30 caratteri). Riprova: ").strip()
            continue
        if password is None:
            password = getpass("   Password admin: ")
            conferma = getpass("   Ripeti la password: ")
        else:
            conferma = password
        errori = errori_password(password, conferma)
        if not errori:
            break
        print("   " + " ".join(errori))
        password = None

    email = (os.environ.get("ADMIN_EMAIL")
             or input("   Email admin (facoltativa, serve per il reset password): ").strip().lower()
             or None)
    if email and not EMAIL_RE.fullmatch(email):
        print("   Email non valida: l'admin viene creato senza email.")
        email = None

    try:
        # l'admin creato dal terminale è già attivo: non deve confermare l'email
        DB_tool.crea_utente(username, hash_password(password), "admin", email=email, attivo=True)
    except (UsernameGiaUsato, EmailGiaUsata):
        # esiste già come utente normale: lo promuovo e lo attivo
        esistente = DB_tool.leggi_utente_per_username(username)
        if not esistente:
            print("   Questa email appartiene a un altro account: riavvia e scegline un'altra.")
            raise SystemExit(1)
        DB_tool.cambia_ruolo(esistente["id"], "admin")
        DB_tool.attiva_utente(esistente["id"])
    print(f" * Amministratore «{username}» creato.\n")


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
            DB_tool.crea_tabelle()  # crea le tabelle dell'app se mancano (non tocca `studenti`)
            if DB_tool.conta_admin() == 0:
                crea_primo_admin()
            print(" * Email:", "MODALITÀ SVILUPPO – i link compaiono qui nel terminale"
                  if mail_tool.modalita_sviluppo()
                  else f"invio tramite {mail_tool.configurazione()['host']}")
            print(f" * Database {DB_tool.DB_CONFIG['database']} su "
                  f"{DB_tool.DB_CONFIG['host']}: {DB_tool.conta_studenti()} studenti, "
                  f"{len(DB_tool.elenco_utenti())} utenti")
        except ErroreDB as e:
            print(f" * ATTENZIONE: {e}\n   L'app mostrerà un errore finché il DB non è raggiungibile.")

    app.run(debug=True, port=5001)
