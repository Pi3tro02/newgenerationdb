-- =============================================================================
-- Script di caricamento dati da file CSV per PostgreSQL (client-side \copy)
-- Variante locale: usa i CSV dalla root del progetto.
-- La variante Docker si trova in database/postgres/02-load_data.sql e usa
-- i path montati sotto /data.
-- =============================================================================
-- Eseguire da terminale posizionandosi nella radice del progetto:
-- psql -h localhost -U fraud -d frauddb -f load_data.sql
-- =============================================================================

-- Caricamento dati anagrafici e di supporto
\copy customers FROM 'customers.csv' WITH (FORMAT csv, HEADER true, DELIMITER ',');
\copy cards FROM 'cards.csv' WITH (FORMAT csv, HEADER true, DELIMITER ',');
\copy merchants FROM 'merchants.csv' WITH (FORMAT csv, HEADER true, DELIMITER ',');

-- -----------------------------------------------------------------------------
-- Verifica del conteggio righe caricate per tutte le tabelle
-- -----------------------------------------------------------------------------
SELECT 'customers' AS tabella, COUNT(*) AS totale_righe FROM customers
UNION ALL
SELECT 'cards' AS tabella, COUNT(*) AS totale_righe FROM cards
UNION ALL
SELECT 'merchants' AS tabella, COUNT(*) AS totale_righe FROM merchants
UNION ALL
SELECT 'transactions' AS tabella, COUNT(*) AS totale_righe FROM transactions
UNION ALL
SELECT 'alerts' AS tabella, COUNT(*) AS totale_righe FROM alerts;
