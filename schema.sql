-- Tabelle create dall'applicazione nel database fgasparini.
-- NON serve eseguirlo a mano: app2.py le crea da solo al primo avvio
-- (DB_tool.crea_tabelle). Serve come documentazione o per crearle da phpMyAdmin.
-- La tabella `studenti` esiste già e la sua struttura non viene modificata.

USE fgasparini;

-- Account dell'applicazione.
--   password_hash: "pbkdf2:sha256:600000$<salt>$<hash>", mai la password in chiaro
--   ruolo:  admin = gestore (CRUD), utente = utente base (sola lettura)
CREATE TABLE IF NOT EXISTS utenti (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(30)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    ruolo         ENUM('admin', 'utente') NOT NULL DEFAULT 'utente',
    creato        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;



