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

## Avvio

```bash
pip install -r requirements.txt
python app2.py
```

Poi apri <http://localhost:5001>.

Credenziali di prova: `ciccio` / `pasticcio1`.
L'app chiede la password del database all'avvio (oppure impostala nel file `.env`, vedi `.env.esempio`).
