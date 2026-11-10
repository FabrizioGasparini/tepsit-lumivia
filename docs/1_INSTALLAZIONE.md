# 1 · Installazione e configurazione

Questa guida porta da zero all'applicazione funzionante sul tuo PC, collegata al database della scuola.

## Cosa serve

- **Python 3.10 o più recente.** Per controllare: `python --version` (su Mac/Linux `python3 --version`).
- **Accesso al database MySQL/MariaDB** della scuola: host `10.10.0.10`, utente `gasparini.fabrizio`, database `fgasparini`, con la tua password. Il PC deve essere sulla rete della scuola (o in VPN).
- Nel database deve esistere la tabella **`studenti`**: le altre tabelle le crea l'applicazione.

## Passo 1 – Installare le librerie

Apri il terminale **dentro la cartella del progetto** (quella con `app2.py`) ed esegui:

```bash
pip install -r requirements.txt
```

Vengono installati Flask (il server web), PyMySQL (il collegamento al database), Pillow (per elaborare le immagini) e python-dotenv (per leggere il file `.env`).

> Se `pip` non viene trovato prova con `python -m pip install -r requirements.txt`.

## Passo 2 – Configurare il file `.env` (consigliato)

Copia il file `.env.esempio` e rinomina la copia in **`.env`** (nella stessa cartella di `app2.py`). Aprilo con un editor e compila almeno:

```
DB_PASSWORD=la_tua_password_del_database
```

Il file `.env` è escluso da Git (vedi `.gitignore`): le password **non finiscono su GitHub**.

Se preferisci non usare il file `.env`, puoi lasciare tutto vuoto: all'avvio l'app chiede la password del database nel terminale.

## Passo 3 – Primo avvio

```bash
python app2.py
```

Al primo avvio succede questo:

1. Se manca la password del database, viene chiesta (mentre la scrivi non si vede).
2. Vengono create, se non esistono, le tabelle `utenti`, `token_email`, `foto_studenti` e `log_attivita`. La tabella `studenti` non viene toccata.
3. Non esistendo ancora nessun gestore, l'app chiede **username, password ed email del primo amministratore**. Questo account è già attivo e non deve confermare l'email.

Quando nel terminale compare `Running on http://127.0.0.1:5001` apri il browser su **<http://localhost:5001>** e accedi con il gestore appena creato.

Per fermare il server: `Ctrl + C` nel terminale.

## Passo 4 – Configurare l'invio delle email

La registrazione richiede la conferma via email. Ci sono due modalità.

### Modalità sviluppo (nessuna configurazione)

Se nel file `.env` la voce `SMTP_HOST` è vuota, le email **non vengono spedite**. Al loro posto:

- il testo dell'email con il link viene **stampato nel terminale** dove gira `app2.py`;
- una copia dell'email viene salvata nella cartella `email_inviate/` (puoi aprirla con doppio clic: si vede come una vera email e il bottone funziona).

È comoda per sviluppare e per una demo senza internet.

### Invio reale con Gmail

1. Usa un account Gmail (va bene anche uno creato apposta per il progetto).
2. Su <https://myaccount.google.com> → **Sicurezza** attiva la **Verifica in due passaggi** (è obbligatoria per il passo successivo).
3. Cerca **"Password per le app"** nella barra di ricerca dell'account Google, crea una nuova password (nome: *Lumivia*) e copia il codice di 16 lettere.
4. Nel file `.env` scrivi:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tuoindirizzo@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
```

(la password è il codice di 16 lettere, **senza spazi**, non la password normale di Gmail).

5. Riavvia `app2.py`: nel terminale deve comparire `Email: invio tramite smtp.gmail.com`.

Per provare l'invio senza passare dal sito:

```bash
python mail_tool.py tuoindirizzo@gmail.com
```

> **Se la rete della scuola blocca la porta 587** l'invio fallisce con un errore di timeout. In quel caso usa l'hotspot del telefono oppure la modalità sviluppo.

### Link nelle email

I link nelle email usano l'indirizzo da cui hai aperto il sito (`http://localhost:5001`), quindi funzionano sul tuo PC. Se vuoi che un compagno o il docente confermino l'account dal loro PC, imposta nel `.env` l'indirizzo del tuo computer in rete, ad esempio:

```
BASE_URL=http://10.10.1.32:5001
```

e avvia il server in modo che sia raggiungibile dalla rete cambiando l'ultima riga di `app2.py` in `app.run(debug=True, port=5001, host="0.0.0.0")`.

## Verifiche veloci

| Comando | A cosa serve |
|---|---|
| `python DB_tool.py` | Prova la connessione al database e mostra quanti studenti e utenti ci sono |
| `python mail_tool.py indirizzo@x.it` | Prova l'invio di un'email |

## Problemi frequenti

**`Access denied for user ... (using password: NO)`**
La password del database non è arrivata all'app. Compila `DB_PASSWORD` nel `.env`, oppure lascia che l'app te la chieda. Attenzione: in PowerShell `set DB_PASSWORD=...` non funziona; il comando corretto è `$env:DB_PASSWORD="..."`.

**`Access denied ... (using password: YES)`**
La password è sbagliata, oppure il tuo utente non può collegarsi dal tuo PC.

**`Can't connect to MySQL server on '10.10.0.10'`**
Non sei sulla rete della scuola, oppure il server è spento.

**`ModuleNotFoundError: No module named 'flask'`** (o `pymysql`, `PIL`, `dotenv`)
Le librerie non sono installate per la versione di Python che stai usando: ripeti il passo 1 con `python -m pip install -r requirements.txt`.

**L'email non arriva**
Controlla lo spam. Verifica nel terminale se c'è un errore di invio. Puoi sempre attivare l'account a mano dall'**Area gestori** con il bottone *Attiva*.

**Ho perso la password del gestore**
Se il gestore ha un'email registrata usa *Password dimenticata?* dalla pagina di login. Altrimenti, da phpMyAdmin, esegui `UPDATE utenti SET ruolo = 'utente' WHERE username = 'nome_admin';`: al successivo avvio, non essendoci gestori, l'app ti farà crearne uno nuovo.
