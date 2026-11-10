# Lumivia – gestionale studenti

Applicazione web in **Python (Flask) + MySQL/MariaDB** per consultare e gestire gli studenti di una scuola.
Gli utenti si registrano e attivano l'account tramite **email di conferma**; i **gestori** possono creare, modificare ed eliminare studenti (con **foto salvate nel database**) e gestire gli altri utenti, mentre gli **utenti base** possono solo consultare i dati.

> Progetto scolastico – Fabrizio Gasparini

---

## Come i requisiti sono stati soddisfatti

| Requisito | Soluzione |
|---|---|
| **Registrazione con email di conferma** | `/registrati` crea l'account **disattivato** e invia un'email con un link personale (valido 24 ore, usabile una sola volta). Finché il link non viene aperto il login è bloccato. È possibile richiedere un nuovo link (`/reinvia-conferma`). L'invio è gestito dal modulo `mail_tool.py`. |
| **Utenti con privilegi diversi** | Ruolo `admin` (**gestore**): CRUD su studenti e foto, gestione degli utenti base (attivazione, cambio ruolo, eliminazione). Ruolo `utente` (**base**): sola lettura. I permessi sono verificati **sul server** con i decoratori `login_richiesto` e `admin_richiesto`, non solo nascondendo i bottoni. |
| **Password crittografate** | Hash **PBKDF2-SHA256** con 600.000 iterazioni e *salt* casuale per ogni utente (`werkzeug.security`). Anche i token dei link email sono salvati solo come hash **SHA-256**. |
| **Protezione da SQL injection** | Tutte le query sono nel modulo `DB_tool.py` e usano **query parametrizzate** (`cursor.execute(sql, parametri)` con `%s`): l'input dell'utente non viene mai concatenato nel codice SQL. In più ogni dato viene validato prima di arrivare al database. |
| **Dashboard con i dati del database** | `/dashboard`: elenco studenti letto dal DB con ricerca, filtri (classe, indirizzo, media minima), statistiche e miniature. I gestori vedono anche i comandi per **creare, modificare ed eliminare**. |
| **Endpoint riservato ai gestori** | `/gestione` (area gestori): riepilogo, account in attesa di conferma (attivabili a mano) e **registro di tutte le operazioni**. Anche `/utenti` e le rotte di modifica sono riservate. |
| **Immagini nel database** | Tabella `foto_studenti` con colonna `MEDIUMBLOB`. Le immagini caricate vengono verificate, ridimensionate e ricodificate con Pillow, poi servite dal DB su `/studenti/<id>/foto`. |

### Funzionalità aggiuntive
- Recupero **password dimenticata** via email, con disconnessione da tutti i dispositivi dopo il cambio.
- **Registro attività**: chi ha fatto cosa e quando.
- **Esporta CSV** dei risultati filtrati (si apre direttamente in Excel).
- Scheda studente con età, barra della media e foto; upload con **drag & drop** e anteprima.
- Interfaccia curata con **tema chiaro e scuro**, transizioni animate tra le pagine, filtri che aggiornano l'elenco **senza ricaricare**, distribuzione delle medie cliccabile, finestre di conferma animate, notifiche a comparsa.
- Indicatore di robustezza della password, pagine di errore curate, layout responsive per smartphone, animazioni disattivate con "riduci movimento".
- Pagina aziendale con **navbar che segue lo scorrimento**.
- Risposte **JSON** su tutte le rotte principali (API con `Authorization: Bearer <token>`).

---

## Avvio rapido

```bash
pip install -r requirements.txt
python app2.py
```

Poi apri <http://localhost:5001>. Al primo avvio vengono chieste la password del database e i dati del primo gestore.

Le istruzioni complete, compresa la configurazione dell'email, sono in **[docs/1_INSTALLAZIONE.md](docs/1_INSTALLAZIONE.md)**.

---

## Architettura

```
 Browser ──HTTP──▶  app2.py  (Flask: rotte, permessi, validazione)
                      │   │
                      │   └──▶ mail_tool.py ──SMTP──▶ server di posta
                      ▼
                   DB_tool.py  (unico modulo con SQL, query parametrizzate)
                      │
                      ▼
               MySQL / MariaDB  (studenti, utenti, token_email,
                                 foto_studenti, log_attivita)
```

| File | Ruolo |
|---|---|
| `app2.py` | Applicazione Flask: rotte, login e ruoli, registrazione, validazione dei dati, upload delle foto |
| `DB_tool.py` | Tutte le funzioni di accesso al database |
| `mail_tool.py` | Invio delle email (SMTP oppure modalità sviluppo) |
| `dati_azienda.py` | Contenuti della pagina `/azienda` |
| `schema.sql` | Struttura delle tabelle create dall'app |
| `templates/` | Pagine HTML (Jinja2), tutte basate su `_base.html` |
| `static/` | `css/app.css` (unico foglio di stile, tema chiaro e scuro), `js/app.js` (animazioni, filtri dal vivo, conferme), `fonts/` (caratteri inclusi) |
| `docs/` | Installazione, guida GitHub, guida tecnica per l'esposizione |

### Database
- `studenti` – tabella esistente: id, nome, cognome, classe, indirizzo, data_nascita, email, media_voti
- `utenti` – account: username, email, hash della password, ruolo, attivo
- `token_email` – hash dei link di conferma/reset con scadenza
- `foto_studenti` – immagini come BLOB
- `log_attivita` – registro delle operazioni

### Rotte principali

| Rotta | Chi |
|---|---|
| `/login`, `/registrati`, `/conferma/<token>`, `/reinvia-conferma`, `/password-dimenticata`, `/reimposta-password/<token>` | tutti |
| `/dashboard`, `/dashboard/export.csv`, `/studenti/<id>`, `/studenti/<id>/foto`, `/azienda`, `/form` | utenti loggati |
| `/studenti/nuovo`, `/studenti/<id>/modifica`, `/studenti/<id>/elimina` | **gestori** |
| `/gestione`, `/utenti`, `/utenti/<id>/attiva`, `/utenti/<id>/ruolo`, `/utenti/<id>/elimina` | **gestori** |

---

## Documentazione
1. [Installazione e configurazione](docs/1_INSTALLAZIONE.md)
2. [Caricare il progetto su GitHub](docs/2_GITHUB.md)
3. [Guida tecnica per l'esposizione](docs/3_GUIDA_ESPOSIZIONE.md)
