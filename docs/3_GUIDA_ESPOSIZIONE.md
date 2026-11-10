# 3 · Guida tecnica per l'esposizione

Questa guida serve a presentare il progetto e a rispondere alle domande del docente. Spiega come è fatto il codice, perché sono state fatte certe scelte e come fare le modifiche più probabili durante l'interrogazione.

---

## 1. Il progetto in due minuti

Lumivia è un'applicazione web per gestire gli studenti di una scuola. È scritta in Python con il framework **Flask** e salva tutto in un database **MySQL/MariaDB**.

Chi visita il sito può registrarsi: riceve un'email con un link e solo dopo averlo aperto l'account diventa attivo. Esistono due tipi di utenti. Gli **utenti base** possono consultare l'elenco degli studenti, cercarli, filtrarli, vedere la scheda di ognuno ed esportare i dati in CSV. I **gestori** (ruolo `admin`) possono in più aggiungere, modificare ed eliminare studenti, caricare le loro foto (che vengono salvate dentro il database), attivare o eliminare utenti, cambiare i ruoli e consultare un'area riservata con il registro di tutte le operazioni.

Le password sono salvate come hash con salt, le query al database sono tutte parametrizzate per impedire la SQL injection e i permessi sono controllati dal server a ogni richiesta.

## 2. Scaletta per la demo

Una sequenza che mostra tutti i requisiti in circa 5 minuti:

1. **Registrazione.** Apri `/registrati` in una finestra in incognito, crea un utente (mostra l'indicatore di robustezza della password). Compare la pagina "Controlla la tua email".
2. **Login bloccato.** Prova ad accedere: l'app risponde che l'account non è attivo e offre il reinvio del link.
3. **Conferma.** Apri l'email (su Gmail, oppure dal terminale/cartella `email_inviate/` in modalità sviluppo), clicca il bottone: l'account si attiva e puoi accedere.
4. **Utente base.** Mostra la dashboard: media generale, distribuzione delle medie (clicca una fascia), ricerca e filtri che aggiornano l'elenco senza ricaricare la pagina, export CSV, scheda di uno studente. Prova anche il tema scuro dal bottone sole/luna. Fai notare che non ci sono bottoni di modifica e che se scrivi a mano `/studenti/nuovo` nell'indirizzo vieni respinto.
5. **Gestore.** Nell'altra finestra accedi come gestore: nella dashboard compaiono *Nuovo studente*, modifica ed elimina. Crea uno studente trascinando una foto, modificalo, mostra la scheda con la foto.
6. **Area gestori.** Apri *Area gestori*: si vedono le operazioni appena fatte nel registro attività. Da *Utenti* promuovi l'utente base a gestore e mostra che nell'altra finestra, ricaricando, compaiono subito i comandi di modifica.
7. **Database.** In phpMyAdmin mostra la tabella `utenti` (la colonna `password_hash` non contiene password leggibili), `token_email` (solo hash) e `foto_studenti` (il BLOB).
8. **SQL injection.** Nel campo di ricerca della dashboard scrivi `' OR 1=1 --`: non succede nulla di strano, il testo viene cercato letteralmente e non restituisce risultati.

---

## 3. Architettura

Il progetto è diviso in **livelli**, ognuno con un compito preciso:

```
 Browser ──HTTP──▶  app2.py         ← logica: rotte, permessi, validazione
                      │    │
                      │    └──▶ mail_tool.py ──▶ server SMTP
                      ▼
                   DB_tool.py       ← unico modulo che contiene SQL
                      │
                      ▼
               MySQL / MariaDB
```

- **`templates/`** (presentazione): le pagine HTML scritte con Jinja2, il linguaggio di template di Flask. Ricevono i dati già pronti e si limitano a mostrarli. Tutte estendono `_base.html` (struttura comune, notifiche, finestra di conferma); `_navbar.html` è la barra di navigazione, `_accesso.html` il layout diviso delle pagine di accesso, `_icone.html` le icone SVG.
- **`static/`** (aspetto e comportamento): `css/app.css` è l'unico foglio di stile di tutto il sito, `js/app.js` l'unico script condiviso, `fonts/` i caratteri inclusi nel progetto.
- **`app2.py`** (logica): definisce le rotte (gli indirizzi del sito), controlla chi è loggato e con che ruolo, valida i dati dei form, elabora le immagini e decide quale pagina mostrare.
- **`DB_tool.py`** (accesso ai dati): contiene **tutte** le query SQL. `app2.py` non scrive mai SQL, chiama solo funzioni come `cerca_studenti()` o `crea_utente()`.
- **`mail_tool.py`**: l'unico punto che parla con il server di posta.

**Perché questa divisione?** Se domani si passasse a PostgreSQL basterebbe riscrivere `DB_tool.py`; se si cambiasse provider email, solo `mail_tool.py`. Inoltre la protezione dalla SQL injection è più facile da garantire, perché tutto l'SQL sta in un solo file ed è facile controllarlo.

## 4. Il viaggio di una richiesta

Cosa succede quando un utente apre `/dashboard?classe=5A`:

1. Il browser invia la richiesta con il **cookie** `token` ricevuto al login.
2. Flask trova la funzione associata alla rotta, `dashboard()` in `app2.py`. Prima di eseguirla passa per il decoratore **`@login_richiesto`**.
3. Il decoratore chiama `utente_attuale()`, che legge il token dal cookie, lo cerca nel dizionario `token_attivi`, controlla che non sia scaduto e **rilegge l'utente dal database** (`DB_tool.leggi_utente`). Se non c'è un utente valido, il browser viene rimandato a `/login`.
4. `dashboard()` chiama `studenti_filtrati()`, che legge i filtri dall'URL con `leggi_filtri()`. La classe `5A` viene accettata solo se esiste davvero tra le classi presenti nel DB (**whitelist**).
5. `DB_tool.cerca_studenti(classe="5A")` costruisce la query aggiungendo `WHERE s.classe = %s` e passa `"5A"` come **parametro separato**.
6. PyMySQL invia la query a MySQL e ottiene le righe. `_pulisci()` converte date e decimali in tipi semplici.
7. `render_template("dashboard.html", ...)` riempie il template con i dati e Flask restituisce l'HTML al browser.

Se la stessa richiesta arriva con l'header `Accept: application/json` o `Authorization: Bearer ...`, la funzione restituisce gli stessi dati in **JSON** (vedi `vuole_json()`): la stessa rotta funziona sia per il sito sia come API.

---

## 5. Login e sessioni

Al login (`login_post()`) l'app cerca l'utente per username e verifica la password con `check_password_hash()`. Se è corretta e l'account è attivo, genera un **token casuale** con `secrets.token_urlsafe(32)` (32 byte casuali, impossibili da indovinare) e lo salva nel dizionario `token_attivi` insieme all'id dell'utente e alla scadenza (`TOKEN_DURATA` = 1 ora).

Il token viene mandato al browser in un **cookie** con due opzioni importanti:

- `HttpOnly`: JavaScript non può leggerlo, quindi un eventuale script malevolo non può rubarlo.
- `SameSite=Lax`: il browser non lo invia nelle richieste POST che partono da altri siti, quindi un sito esterno non può far eseguire azioni a nome dell'utente (protezione da **CSRF**).

Il **logout** (`/logout`, solo POST) toglie il token da `token_attivi`, quindi il token non vale più nemmeno se qualcuno l'avesse copiato, e cancella il cookie.

**Perché il ruolo viene riletto dal DB a ogni richiesta?** Così, se un gestore declassa o elimina un utente, l'effetto è immediato: alla richiesta successiva quell'utente non ha più i permessi.

**Login con username inesistente.** Anche in quel caso viene calcolato un hash (`HASH_FINTO`), così la risposta impiega lo stesso tempo: misurando i tempi non si scopre quali username esistono.

## 6. Password

Le password sono salvate con `generate_password_hash(password, method="pbkdf2:sha256:600000")`. Nel database finisce una stringa così:

```
pbkdf2:sha256:600000$Kq3v...salt...$9f2c...hash...
```

- **Hash**: una funzione a senso unico. Dalla password si ottiene l'hash, ma dall'hash non si risale alla password. Al login si ricalcola l'hash della password inserita e lo si confronta con quello salvato.
- **Salt**: una stringa casuale diversa per ogni utente, aggiunta alla password prima dell'hash. Così due utenti con la stessa password hanno hash diversi e non si possono usare tabelle di hash precalcolati (*rainbow table*).
- **600.000 iterazioni**: lo SHA-256 viene ripetuto 600.000 volte. Per un utente che fa login la differenza è di pochi millisecondi, ma per chi prova miliardi di password a forza bruta diventa lentissimo.

**Perché non MD5 o SHA-256 semplici?** Sono pensati per essere velocissimi: una scheda video ne calcola miliardi al secondo, quindi una password debole si scopre in pochi secondi. MD5 inoltre è considerato rotto. PBKDF2-SHA256 è sempre basato su SHA-256, ma con salt e iterazioni, ed è lo standard raccomandato.

Requisiti della password (`errori_password()`): almeno 8 caratteri, almeno una lettera e un numero. Il controllo è fatto sul server; l'indicatore colorato nella pagina è solo un aiuto visivo.

## 7. Registrazione e conferma via email

Il flusso, nelle funzioni di `app2.py`:

1. **`registrati()`** valida username, email e password, poi crea l'utente con `attivo = 0` e ruolo `utente`. Chi si registra non può mai diventare gestore da solo.
2. **`invia_link_conferma()`** genera un token casuale, salva nel DB **solo il suo hash SHA-256** (`hash_token()`) con scadenza 24 ore e chiama `mail_tool.invia_conferma()` con il link `/conferma/<token>`.
3. Se l'email non parte, l'utente appena creato viene cancellato: altrimenti resterebbe un account impossibile da attivare.
4. **`conferma_account(token)`** calcola l'hash del token ricevuto e lo cerca nel DB con `DB_tool.utente_da_token()`. Se esiste e non è scaduto, il token viene **cancellato** (si usa una sola volta) e l'utente attivato.
5. Al login, se la password è giusta ma `attivo = 0`, la risposta è *"Account non ancora attivato"* con il link per un nuovo invio.

**Perché salvare l'hash del token e non il token?** Il token è come una password temporanea: chi lo conosce attiva l'account o, nel caso del reset, cambia la password. Se qualcuno leggesse la tabella `token_email` troverebbe solo hash inutilizzabili.

**Altri accorgimenti:**

- Ogni nuovo invio cancella i token precedenti: vale solo l'ultimo link.
- Tra un invio e l'altro devono passare almeno 60 secondi (`SECONDI_TRA_EMAIL`), per evitare che qualcuno usi il sito per inondare di email una casella.
- Le pagine *reinvia conferma* e *password dimenticata* rispondono sempre "se esiste un account, riceverai un'email", che l'indirizzo sia registrato o no: così non si può usare il sito per scoprire quali email sono iscritte.
- L'email ha una versione HTML e una solo testo (`EmailMessage.add_alternative`), con stili *inline* perché molti client di posta ignorano i fogli di stile.

**Modalità sviluppo.** Se `SMTP_HOST` non è impostato, `mail_tool.invia()` non spedisce nulla: stampa l'email nel terminale e la salva in `email_inviate/`. Questo permette di sviluppare e fare la demo anche senza un server di posta.

**Invio reale.** `smtplib` si collega al server SMTP (es. `smtp.gmail.com:587`), avvia la cifratura con `STARTTLS`, fa il login con la *password per le app* e invia il messaggio.

## 8. Password dimenticata

Funziona come la conferma, con un token di tipo `reset` valido 60 minuti:

1. `/password-dimenticata`: l'utente inserisce l'email e riceve il link `/reimposta-password/<token>`.
2. Aprendo il link (GET) il token viene solo **controllato** (`consuma=False`), così la pagina si può ricaricare.
3. Al salvataggio (POST) il token viene **consumato**, la password aggiornata e tutte le sessioni dell'utente vengono chiuse (`revoca_sessioni_utente()`): se qualcuno gli aveva rubato l'accesso, viene buttato fuori.

## 9. SQL injection

La SQL injection avviene quando l'input dell'utente viene incollato dentro il testo della query. Esempio **sbagliato**:

```python
sql = "SELECT * FROM utenti WHERE username = '" + username + "'"
```

Se l'utente scrive `' OR '1'='1` la query diventa `... WHERE username = '' OR '1'='1'` e restituisce tutti gli utenti.

Nel progetto **tutte** le query usano i **parametri**:

```python
cur.execute("SELECT ... FROM utenti WHERE username = %s", (username,))
```

Query e dati viaggiano separati: è il driver PyMySQL a fare l'*escape* dei caratteri speciali, quindi qualsiasi cosa scriva l'utente resta un **valore** e non diventa mai codice SQL.

Ci sono anche altre difese:

- I filtri `classe` e `indirizzo` sono accettati solo se presenti nell'elenco letto dal DB (`leggi_filtri()`).
- Nella ricerca libera, i caratteri jolly di `LIKE` (`%` e `_`) vengono neutralizzati, così cercare `%` non restituisce tutto.
- Nelle stringhe SQL vengono inseriti solo nomi di colonne scritti nel codice (es. `CAMPI_STUDENTE`), mai testo dell'utente.

## 10. Ruoli e permessi

I due decoratori in `app2.py`:

```python
@app.route("/studenti/nuovo", methods=["GET", "POST"])
@admin_richiesto
def nuovo_studente(): ...
```

- `@login_richiesto`: se non c'è un utente valido, rimanda a `/login` (o risponde 401 in JSON).
- `@admin_richiesto`: in più controlla `ruolo == "admin"`; altrimenti mostra un messaggio e rimanda alla dashboard (o risponde 403 in JSON).

**Il punto chiave:** nascondere i bottoni nel template **non basta**. Un utente base potrebbe scrivere l'indirizzo a mano o mandare una richiesta POST con un programma. Per questo il controllo è sul server, su ogni rotta di modifica.

Regole sugli utenti: un gestore non può cambiare il proprio ruolo né eliminare sé stesso. Così resta sempre almeno un gestore.

## 11. Immagini nel database

Il percorso di una foto:

1. Il form di `studente_form.html` ha `enctype="multipart/form-data"`, necessario per inviare file. Il JavaScript gestisce il drag & drop e l'anteprima.
2. Flask rifiuta subito i file sopra i 5 MB (`MAX_CONTENT_LENGTH`).
3. `elabora_foto()` apre il file con **Pillow**, controlla che sia davvero un JPG/PNG/WEBP/GIF (non basta l'estensione: un file di testo rinominato `.jpg` viene rifiutato), lo raddrizza secondo i dati EXIF, lo riduce a massimo 600×600 px e lo **ricodifica in JPEG**. Ricodificare elimina anche eventuali dati nascosti nel file e i metadati (es. la posizione GPS dello scatto).
4. `DB_tool.salva_foto()` salva i byte nella colonna `MEDIUMBLOB` di `foto_studenti` con `INSERT ... ON DUPLICATE KEY UPDATE`, così la stessa funzione inserisce la prima foto o sostituisce quella vecchia.
5. Per mostrarla, il tag `<img src="/studenti/4/foto">` chiama `foto_studente()`, che legge i byte dal DB e li restituisce con il giusto tipo (`image/jpeg`). Anche questa rotta richiede il login.

**BLOB nel database o file su disco?** Il requisito chiedeva il database. Vantaggi: un solo backup contiene tutto, le foto sono protette dagli stessi permessi dei dati e non si perdono spostando il server. Svantaggi: il DB diventa più pesante e ogni immagine passa dal server Python. Il ridimensionamento a 600 px (circa 30–80 KB per foto) limita molto il problema.

Le foto sono in una tabella separata e non in una colonna di `studenti`. Così la tabella originale non viene modificata e le query dell'elenco restano leggere: il BLOB viene letto solo quando serve l'immagine.

## 12. Dashboard e filtri

`DB_tool.cerca_studenti()` costruisce la clausola `WHERE` in modo **dinamico**: parte da due liste vuote, `condizioni` e `parametri`, e per ogni filtro compilato aggiunge un pezzo:

```python
if classe:
    condizioni.append("s.classe = %s")
    parametri.append(classe)
...
sql += " WHERE " + " AND ".join(condizioni)
```

La query usa un `LEFT JOIN` con `foto_studenti` per sapere quali studenti hanno una foto (`ha_foto`) senza scaricare i BLOB. Le statistiche in alto (`statistiche()`) sono calcolate dal database con `COUNT`, `AVG` e `SUM`.

I filtri funzionano **senza ricaricare la pagina**: quando cambia un campo, `app.js` chiede al server la stessa pagina con i nuovi parametri (`fetch`), la legge con `DOMParser` e sostituisce solo l'elenco dei risultati, la legenda e il link di esportazione. La ricerca testuale parte 300 ms dopo che si smette di scrivere (*debounce*), per non fare una richiesta a ogni lettera; se arriva una nuova richiesta mentre la precedente è in corso, quella vecchia viene annullata (`AbortController`). Il filtraggio resta comunque fatto dal **server con la query SQL**: JavaScript cambia solo il modo in cui la pagina si aggiorna, e senza JavaScript il form funziona lo stesso inviandosi normalmente.

La barra **"Come sono distribuite le medie"** divide gli studenti in quattro fasce (sotto il 6, 6–7, 7–8, 8 e oltre), calcolate dal database in `statistiche()` con `SUM(media_voti < 6)` e simili. Cliccando una fascia si applicano i filtri `media_min` e `media_max`.

I filtri stanno nell'URL (`?classe=5A&media_min=7`), quindi un risultato filtrato si può salvare nei preferiti o condividere, e il pulsante *Esporta CSV* esporta esattamente quello che si sta vedendo.

## 13. Area gestori e registro attività

`/gestione` è l'endpoint riservato ai gestori. Mostra:

- il riepilogo (studenti, foto nel DB, utenti attivi, account in attesa);
- gli account che non hanno ancora confermato l'email, con il bottone per attivarli a mano;
- il **registro attività**, letto dalla tabella `log_attivita`.

Il registro viene scritto dalla funzione `registra()` dopo ogni operazione importante: registrazione, conferma, reset password, creazione, modifica ed eliminazione di studenti, cambio ruolo, attivazione ed eliminazione di utenti. È scritta in modo da **non bloccare mai** l'operazione principale: se la scrittura del log fallisce, l'errore viene annotato ma l'utente non se ne accorge.

## 14. Altre protezioni

- **XSS (iniezione di HTML/JavaScript):** Jinja2 fa l'*escape* automatico di tutto ciò che viene stampato con `{{ ... }}`. Se qualcuno salva come nome `<script>...</script>`, viene mostrato come testo e non eseguito.
- **Le azioni che modificano dati sono tutte POST**, mai GET. Un link o un'immagine su un altro sito non può far eliminare uno studente.
- **Validazione lato server** di tutti i campi (`valida_studente()`): classe nel formato `3A`, email valida, data plausibile, media tra 0 e 10. I controlli HTML del browser sono solo una comodità, perché si possono aggirare.
- **Redirect solo verso pagine conosciute:** il campo `torna` delle azioni sugli utenti accetta solo due valori (`torna_indietro()`), così nessuno può usare il sito per rimandare a un indirizzo esterno.
- **Segreti fuori dal codice:** password del DB e dell'email stanno nel file `.env`, escluso da Git.

## 15. Il database

| Tabella | Contenuto | Note |
|---|---|---|
| `studenti` | dati degli studenti | già esistente, la struttura non viene toccata |
| `utenti` | username, email, `password_hash`, ruolo, attivo | `username` ed `email` sono `UNIQUE` |
| `token_email` | hash del token, utente, tipo, scadenza | un token per tipo per utente |
| `foto_studenti` | `studente_id`, `dati` (MEDIUMBLOB), mime | una foto per studente |
| `log_attivita` | chi, azione, dettaglio, quando | indice su `quando` |

`DB_tool.crea_tabelle()` usa `CREATE TABLE IF NOT EXISTS`, quindi si può eseguire a ogni avvio. Contiene anche una piccola **migrazione**: se trova una tabella `utenti` creata da una versione precedente senza le colonne `email` e `attivo`, le aggiunge con `ALTER TABLE` (controllando prima in `information_schema`).

L'eliminazione di uno studente cancella anche la sua foto **nella stessa transazione** (`elimina_studente()`): o riescono entrambe le `DELETE` o nessuna. La funzione `connessione()` fa `commit` se tutto va bene e `rollback` se c'è un errore.

## 16. L'interfaccia

L'aspetto è costruito come un piccolo **design system**: un solo file `static/css/app.css` definisce all'inizio dei *token* (variabili CSS come `--blu`, `--rosso`, `--superficie`, `--r-m` per i raggi degli angoli) e tutti i componenti li riusano. Cambiando un token cambia tutto il sito in modo coerente.

**Scelte da saper giustificare:**

- **Colori con un significato.** C'è un solo colore di accento, il blu della penna a sfera; il rosso, come la penna della correzione, compare solo dove ha un significato: medie insufficienti, errori, eliminazioni. Le medie sono scritte in blu, in verde da 8 in su e in rosso sotto il 6.
- **Tema scuro.** Lo stesso foglio di stile ridefinisce i token sotto `:root[data-tema="scuro"]`. Il tema iniziale segue l'impostazione del sistema operativo, il bottone sole/luna lo cambia e la scelta viene ricordata nel browser (`localStorage`). Un piccolo script nell'`<head>` applica il tema prima di disegnare la pagina, così non c'è il "lampo" bianco.
- **Font inclusi nel progetto** (`static/fonts/`, licenza libera OFL): Bricolage Grotesque per i titoli e Instrument Sans per i testi. Non dipendono da Google Fonts, quindi funzionano anche senza internet o se la rete della scuola blocca siti esterni.
- **Animazioni.** Le transizioni tra pagine usano la **View Transitions API** del browser (`@view-transition { navigation: auto; }`): la barra di navigazione resta ferma e il contenuto sfuma. Ci sono poi la pillola che scorre sotto la voce attiva, i numeri che contano (`data-conta`), le barre che crescono quando entrano nello schermo (`IntersectionObserver`), le righe della tabella che entrano in sequenza (ritardo calcolato con la variabile CSS `--i`), la timeline che si disegna durante lo scroll (`animation-timeline: view()`), le notifiche con la barra del tempo e la finestra di conferma (`<dialog>`) al posto del `confirm()` del browser.
- **Accessibilità.** Con l'impostazione di sistema "riduci movimento" (`prefers-reduced-motion`) le animazioni vengono disattivate. I bottoni con sola icona hanno un `aria-label`, il focus da tastiera è sempre visibile, il tasto `/` porta alla ricerca ed `Esc` chiude menu e finestre.
- **Miglioramento progressivo.** JavaScript aggiunge comodità ma non è indispensabile: i form, i filtri e i link funzionano anche senza.

## 17. Limiti noti e possibili miglioramenti

Saper indicare i limiti del proprio progetto è un punto a favore.

- **Le sessioni sono in memoria** (dizionario `token_attivi`): se il server si riavvia, tutti devono rifare il login. Miglioramento: salvarle in una tabella del DB o usare Redis.
- **Server di sviluppo**: `app.run(debug=True)` va bene per la scuola. In produzione si userebbero un server WSGI (es. Gunicorn o Waitress), `debug=False` e HTTPS con il cookie `Secure`.
- **CSRF**: la protezione si basa su `SameSite=Lax`, supportato da tutti i browser moderni. Si potrebbe aggiungere un token CSRF in ogni form (es. con Flask-WTF).
- **Nessun limite ai tentativi di login**: si potrebbe bloccare un account o un IP dopo un certo numero di errori.
- **Paginazione**: con migliaia di studenti servirebbe mostrarli a pagine (`LIMIT` / `OFFSET`).

---

## 18. Domande probabili (e risposte)

**Dove vengono controllati i permessi?**
Nei decoratori `login_richiesto` e `admin_richiesto` in `app2.py`, applicati a ogni rotta. Il ruolo viene riletto dal database a ogni richiesta.

**Come fai a sapere chi sta facendo la richiesta?**
Dal cookie `token`, che contiene un valore casuale generato al login. Il server lo cerca in `token_attivi` per sapere a quale utente corrisponde.

**Cosa succede se qualcuno ruba il database?**
Trova hash delle password con salt e 600.000 iterazioni, difficilissimi da invertire, e hash dei token email, inutilizzabili. Non trova password in chiaro.

**Perché il token dell'email è così lungo?**
32 byte casuali significano 2²⁵⁶ possibilità: provare a indovinarlo è impossibile. È generato con il modulo `secrets`, pensato per la crittografia (il modulo `random` invece è prevedibile).

**Cosa succede se apro due volte il link di conferma?**
La seconda volta il token non esiste più, perché è stato cancellato al primo uso: compare "Link non valido" con l'offerta di richiederne uno nuovo.

**Come viene salvata l'immagine?**
Come sequenza di byte in una colonna `MEDIUMBLOB` della tabella `foto_studenti`, dopo essere stata verificata e ridimensionata con Pillow.

**Perché `DB_tool.py` separato?**
Per separare la logica dall'accesso ai dati: tutto l'SQL è in un posto solo, più facile da controllare per la sicurezza e da cambiare.

**Cos'è un decoratore?**
Una funzione che "avvolge" un'altra funzione per aggiungere un comportamento prima o dopo. `@login_richiesto` esegue il controllo del login prima della funzione della rotta, senza riscriverlo in ogni rotta.

**Cosa fa `@wraps(f)`?**
Copia nome e documentazione della funzione originale nel wrapper. Senza, Flask vedrebbe tutte le rotte decorate con lo stesso nome (`wrapper`) e darebbe errore.

**Perché `redirect(..., code=303)` dopo un POST?**
È il pattern **Post/Redirect/Get**: dopo aver salvato si rimanda a una pagina GET, così se l'utente ricarica la pagina il form non viene inviato una seconda volta.

**Come fa la tabella ad aggiornarsi senza ricaricare la pagina?**
`app.js` intercetta i cambiamenti del form dei filtri, chiede la pagina al server con `fetch` e sostituisce solo i pezzi indicati in `data-aggiorna`. Il filtro vero lo fa comunque il server con la query SQL.

**Perché non usare un framework come React?**
Per un'applicazione di questa dimensione le pagine generate dal server con Jinja sono più semplici, più veloci da caricare e funzionano anche senza JavaScript. Il poco JavaScript necessario sta in un solo file senza dipendenze.

**Cos'è `g` in Flask?**
Un oggetto che vive per la durata di una singola richiesta. `utente_attuale()` ci salva l'utente letto dal DB, così nella stessa richiesta il DB viene interrogato una volta sola anche se la funzione è chiamata più volte.

**Cosa succede se il database è spento?**
`DB_tool.connessione()` solleva `ErroreDB`. Se succede dentro una pagina, viene intercettato da `@app.errorhandler(ErroreDB)` e l'utente vede la pagina "Database non disponibile" con il motivo. Se succede nel controllo del login (`utente_attuale()`), l'utente viene considerato non loggato e rimandato a `/login`, dove il tentativo di accesso mostra il messaggio d'errore del database. In nessun caso compare un errore generico del server.

---

## 19. Modifiche "dal vivo" più probabili

Per ognuna: dove intervenire e cosa scrivere.

### Cambiare la durata della sessione o dei link
In cima ad `app2.py`: `TOKEN_DURATA = 3600` (secondi), `ORE_VALIDITA_CONFERMA = 24`, `MINUTI_VALIDITA_RESET = 60`.

### Rendere la password più robusta (es. almeno 10 caratteri e un simbolo)
In `errori_password()` in `app2.py`:

```python
if len(password) < 10:
    errori.append("La password deve avere almeno 10 caratteri.")
if not re.search(r"[^A-Za-z0-9]", password):
    errori.append("La password deve contenere almeno un simbolo.")
```

### Aggiungere un filtro alla dashboard (es. anno di nascita)
1. **`DB_tool.cerca_studenti()`**: aggiungi il parametro `anno=None` e
   ```python
   if anno:
       condizioni.append("YEAR(s.data_nascita) = %s")
       parametri.append(anno)
   ```
2. **`app2.leggi_filtri()`**: leggi e valida il valore
   ```python
   filtri["anno"] = None
   if (args.get("anno") or "").isdigit():
       filtri["anno"] = int(args["anno"])
   ```
3. **`templates/dashboard.html`**: dentro il `<form class="filtri">`, dopo il campo della media minima, aggiungi
   ```html
   <div class="campo">
       <label class="sr" for="anno">Anno di nascita</label>
       <input type="number" id="anno" name="anno" placeholder="Anno di nascita"
              value="{{ filtri.anno or '' }}">
   </div>
   ```
4. **`static/css/app.css`**: nella regola `.filtri` passa da 3 a 4 colonne piccole:
   `grid-template-columns: minmax(0, 2.2fr) repeat(4, minmax(0, 1fr));`

Il filtro funziona subito anche "dal vivo", perché `app.js` invia automaticamente tutti i campi del form.

### Cambiare l'ordinamento della dashboard (es. per media decrescente)
In `DB_tool.cerca_studenti()` cambia l'ultima riga in `sql += " ORDER BY s.media_voti DESC, s.cognome"`.

### Aggiungere una colonna al CSV
In `app2.esporta_csv()` aggiungi l'intestazione in `writerow([...])` e il valore nella riga dentro il ciclo `for s in righe`.

### Dare a un'altra operazione il permesso solo ai gestori
Aggiungi `@admin_richiesto` sotto `@app.route(...)` della rotta.

### Aggiungere un terzo ruolo (es. `docente`)
1. Nel DB: `ALTER TABLE utenti MODIFY ruolo ENUM('admin','docente','utente') NOT NULL DEFAULT 'utente';`
2. In `DB_tool.py`: `RUOLI = ("admin", "docente", "utente")`.
3. In `app2.py` un decoratore come `admin_richiesto` che accetta `ruolo in ("admin", "docente")`.
4. In `templates/utenti.html` aggiungi `<option value="docente">` al menu del ruolo.

### Mostrare un nuovo dato nella scheda studente
In `templates/studente.html`, dentro `<dl class="dettagli">` aggiungi un blocco come gli altri:
```html
<div><dt>Indirizzo</dt><dd>{{ s.indirizzo }}</dd></div>
```

### Cambiare il testo dell'email di conferma
In `mail_tool.invia_conferma()`: modifica le variabili `saluto`, `testo` e `nota`.

### Limitare la dimensione massima delle foto
In `app2.py`: `app.config["MAX_CONTENT_LENGTH"]` (byte del file caricato) e `LATO_MAX_FOTO` (lato massimo in pixel dopo il ridimensionamento).

---

## 20. Glossario veloce

- **Flask**: micro-framework Python per applicazioni web. Una funzione decorata con `@app.route` risponde a un indirizzo.
- **Jinja2**: linguaggio dei template; `{{ variabile }}` stampa un valore, `{% if %}` / `{% for %}` sono le istruzioni.
- **Rotta / endpoint**: un indirizzo del sito associato a una funzione.
- **CRUD**: *Create, Read, Update, Delete*, le quattro operazioni base sui dati.
- **Hash**: funzione a senso unico che trasforma un testo in un'impronta di lunghezza fissa.
- **Salt**: valore casuale aggiunto alla password prima dell'hash.
- **Token**: stringa casuale che identifica una sessione o autorizza un'azione (link email).
- **Cookie HttpOnly**: cookie che JavaScript non può leggere.
- **BLOB**: *Binary Large Object*, colonna del DB che contiene dati binari (le immagini).
- **SMTP**: protocollo per inviare email.
- **STARTTLS**: comando che rende cifrata una connessione SMTP già aperta.
- **Query parametrizzata**: query in cui i valori sono passati separatamente dal testo SQL.
- **Transazione**: gruppo di operazioni sul DB che riescono tutte o nessuna (`commit` / `rollback`).
