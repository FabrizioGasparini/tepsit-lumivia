# Lumivia – gestionale studenti

Applicazione web in **Python (Flask) + MySQL/MariaDB** per gestire gli studenti di una scuola.

> Progetto scolastico – Fabrizio Gasparini · in sviluppo

## Funzionalità

- Login con token di sessione in un cookie `HttpOnly`
- Modulo di richiesta con riepilogo
- Logout che revoca il token sul server
- Dashboard degli studenti con ricerca e filtri (classe, indirizzo, media minima)
- Pagina aziendale con barra di navigazione tra le sezioni
- Dati della dashboard letti dal database MySQL tramite il modulo `DB_tool.py` (query parametrizzate contro la SQL injection)
- Scheda di ogni studente
- Registrazione degli utenti con password salvate come hash PBKDF2-SHA256 con salt
- Ruoli: **gestore** (admin) e **utente base** (sola lettura); pagina di gestione degli utenti

## Avvio

```bash
pip install -r requirements.txt
python app2.py
```

Poi apri <http://localhost:5001>.

L'app chiede la password del database all'avvio (oppure impostala nel file `.env`, vedi `.env.esempio`).
Al primo avvio vengono create le tabelle dell'applicazione e viene chiesto di creare il primo gestore.
