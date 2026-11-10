-- Tabelle create dall'applicazione nel database fgasparini.
-- NON serve eseguirlo a mano: app2.py le crea da solo al primo avvio
-- (DB_tool.crea_tabelle). Serve come documentazione o per crearle da phpMyAdmin.
-- La tabella `studenti` esiste già e la sua struttura non viene modificata.

USE fgasparini;

-- Account dell'applicazione.
--   password_hash: "pbkdf2:sha256:600000$<salt>$<hash>", mai la password in chiaro
--   ruolo:  admin = gestore (CRUD), utente = utente base (sola lettura)
--   attivo: 0 finché l'utente non apre il link nell'email di conferma
CREATE TABLE IF NOT EXISTS utenti (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(30)  NOT NULL UNIQUE,
    email         VARCHAR(100) NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    ruolo         ENUM('admin', 'utente') NOT NULL DEFAULT 'utente',
    attivo        TINYINT(1) NOT NULL DEFAULT 0,
    creato        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Link inviati per email (conferma account e reset password).
-- Si salva solo l'hash SHA-256 del token: il token vero esiste solo nell'email.
CREATE TABLE IF NOT EXISTS token_email (
    token_hash CHAR(64) PRIMARY KEY,
    utente_id  INT NOT NULL,
    tipo       ENUM('attivazione', 'reset') NOT NULL,
    scadenza   DATETIME NOT NULL,
    creato     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_utente (utente_id, tipo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Foto degli studenti salvate come BLOB (una per studente).
-- Le immagini vengono ridimensionate a max 600x600 e salvate in JPEG.
CREATE TABLE IF NOT EXISTS foto_studenti (
    studente_id INT PRIMARY KEY,          -- = studenti.id
    dati        MEDIUMBLOB  NOT NULL,     -- i byte dell'immagine (max 16 MB)
    mime        VARCHAR(50) NOT NULL,     -- es. image/jpeg
    dimensione  INT         NOT NULL,     -- in byte
    caricata    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Registro delle operazioni (visibile nell'area gestori).
CREATE TABLE IF NOT EXISTS log_attivita (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    utente_id INT NULL,
    username  VARCHAR(30) NULL,
    azione    VARCHAR(30) NOT NULL,
    dettaglio VARCHAR(255) NOT NULL DEFAULT '',
    quando    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_quando (quando)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
