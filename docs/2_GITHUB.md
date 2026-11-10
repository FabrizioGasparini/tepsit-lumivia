# 2 · Caricare il progetto su GitHub

Procedura che segue le istruzioni del docente: si crea la repository dal sito, la si clona, ci si copiano dentro i file e si fa il push.

## Prima volta in assoluto: configurare Git

Se non l'hai mai fatto su questo PC, nel terminale:

```bash
git config --global user.name "Fabrizio Gasparini"
git config --global user.email "la.tua.email@example.com"
```

Usa la stessa email del tuo account GitHub.

## Passo 1 – Creare la repository dal sito

1. Vai su <https://github.com> e accedi.
2. In alto a destra **+** → **New repository**.
3. *Repository name*: ad esempio `lumivia-gestionale-studenti`.
4. Visibilità: **Private** se la condividerai solo con i docenti (consigliato), oppure Public.
5. **Non** spuntare "Add a README file", ".gitignore" o "license": li abbiamo già nel progetto.
6. **Create repository**.
7. Copia l'URL che compare (il bottone verde **Code** → HTTPS), tipo `https://github.com/TUO-UTENTE/lumivia-gestionale-studenti.git`.

## Passo 2 – Clonare la repository

Nel terminale, spostati nella cartella in cui vuoi tenere il progetto (ad esempio Documenti) ed esegui:

```bash
git clone https://github.com/TUO-UTENTE/lumivia-gestionale-studenti.git
```

Si crea una cartella vuota `lumivia-gestionale-studenti` (contiene solo la cartella nascosta `.git`).

## Passo 3 – Copiare i file del progetto

Copia **tutto il contenuto** della cartella `progetto` (quella estratta dallo zip) dentro la cartella appena clonata. Devono finire allo stesso livello di `.git`:

```
lumivia-gestionale-studenti/
├── .git/                (creata da git clone)
├── .gitignore
├── .env.esempio
├── README.md
├── app2.py
├── DB_tool.py
├── mail_tool.py
├── dati_azienda.py
├── requirements.txt
├── schema.sql
├── docs/
├── static/              (css, js e font)
└── templates/
```

> **Attenzione ai file nascosti:** `.gitignore` e `.env.esempio` iniziano con il punto. Su Mac il Finder li nasconde (`Cmd + Shift + .` per vederli); su Windows attiva *Visualizza → Elementi nascosti*. Assicurati di copiarli.

> **Non copiare** il tuo file `.env` personale con le password: comunque il `.gitignore` impedisce che venga caricato.

## Passo 4 – Commit e push

Dal terminale, **dentro la cartella della repository**:

```bash
cd lumivia-gestionale-studenti
git status
```

I file nuovi compaiono **in rosso** (non ancora aggiunti). Poi:

```bash
git add .
git status
```

Ora sono **in verde**. Controlla che nella lista **non** ci siano `.env`, `__pycache__` o `email_inviate`. Poi:

```bash
git commit -m "Prima versione: login con ruoli, conferma email, dashboard CRUD, foto nel DB"
git push
```

### Autenticazione al primo push

Git chiede username e password:

- **Username:** il tuo username di GitHub.
- **Password:** **non** la password di GitHub ma un **token**. Per crearlo: GitHub → foto profilo → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)** → **Generate new token (classic)**. Dai un nome, scegli una scadenza (almeno dopo il 2 dicembre), spunta lo scope **repo** e genera. Copia subito il token (non verrà più mostrato) e incollalo come password.

> Nel terminale, mentre incolli il token non compare nulla: è normale, premi Invio.

Ricarica la pagina della repository su GitHub: ci devono essere tutti i file e il README mostrato in basso.

## Passo 5 – Condividere la repository con i docenti

Se la repository è privata: nella pagina della repository → **Settings** → **Collaborators** → **Add people**, inserisci lo username o l'email GitHub di ogni docente. Riceveranno un invito da accettare.

Se è pubblica basta mandare il link.

## Modifiche successive

Ogni volta che cambi qualcosa:

```bash
git status
git add .
git commit -m "Descrizione breve della modifica"
git push
```

Scrivi messaggi di commit chiari ("Aggiunto filtro per classe", "Corretto errore nel reset password"): i docenti possono vedere la storia del progetto nella scheda **Commits**.

## Checklist prima della consegna (2 dicembre)

- [ ] L'app parte collegata al **database della scuola** (`python DB_tool.py` funziona).
- [ ] Esiste almeno un **gestore** e almeno un **utente base** di prova.
- [ ] Registrazione e **conferma email** provate (con Gmail o in modalità sviluppo).
- [ ] Alcuni studenti hanno una **foto** caricata.
- [ ] Repository su GitHub con tutti i file, **senza** `.env`.
- [ ] Docenti aggiunti come **collaboratori** (o link pubblico inviato).
- [ ] Riletta la [guida tecnica per l'esposizione](3_GUIDA_ESPOSIZIONE.md).
