-- =============================================================================
-- Script di caricamento dati da file CSV per PostgreSQL (client-side \copy)
-- =============================================================================
-- Eseguire questo script con il client psql posizionandosi nella cartella dei CSV:
-- psql -h localhost -U fraud -d frauddb -f database/postgres/load_data.sql
-- =============================================================================

-- Caricamento dati anagrafici e di supporto
\copy customers FROM '/data/customers.csv' WITH (FORMAT csv, HEADER true, DELIMITER ',');
\copy cards FROM '/data/cards.csv' WITH (FORMAT csv, HEADER true, DELIMITER ',');
\copy merchants FROM '/data/merchants.csv' WITH (FORMAT csv, HEADER true, DELIMITER ',');

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
