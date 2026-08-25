-- =============================================================================
-- Schema PostgreSQL per il sistema di rilevamento frodi (frauddb)
-- =============================================================================

DROP TABLE IF EXISTS alerts CASCADE;
DROP TABLE IF EXISTS transactions CASCADE;
DROP TABLE IF EXISTS merchants CASCADE;
DROP TABLE IF EXISTS cards CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

-- -----------------------------------------------------------------------------
-- Tabella: customers (5000 righe attese)
-- -----------------------------------------------------------------------------
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name VARCHAR(50),
    home_country VARCHAR(50),
    risk_profile VARCHAR(10) CHECK (risk_profile IN ('low', 'medium', 'high')),
    avg_transaction_amount NUMERIC(10,2),
    created_at TIMESTAMP
);

COMMENT ON TABLE customers IS 'Tabella dei clienti (5000 righe attese)';
COMMENT ON COLUMN customers.customer_id IS 'Identificativo univoco del cliente (Primary Key)';
COMMENT ON COLUMN customers.name IS 'Nome del cliente';
COMMENT ON COLUMN customers.home_country IS 'Paese di residenza del cliente';
COMMENT ON COLUMN customers.risk_profile IS 'Profilo di rischio del cliente (low, medium, high)';
COMMENT ON COLUMN customers.avg_transaction_amount IS 'Importo medio delle transazioni';
COMMENT ON COLUMN customers.created_at IS 'Data e ora di creazione del profilo cliente';

-- -----------------------------------------------------------------------------
-- Tabella: cards (6000 righe attese)
-- -----------------------------------------------------------------------------
CREATE TABLE cards (
    card_id INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(customer_id),
    card_type VARCHAR(10) CHECK (card_type IN ('debit', 'credit')),
    card_status VARCHAR(10) CHECK (card_status IN ('active', 'flagged', 'blocked')),
    daily_limit INTEGER
);

COMMENT ON TABLE cards IS 'Tabella delle carte di pagamento (6000 righe attese)';
COMMENT ON COLUMN cards.card_id IS 'Identificativo univoco della carta (Primary Key)';
COMMENT ON COLUMN cards.customer_id IS 'Riferimento al cliente (Foreign Key -> customers)';
COMMENT ON COLUMN cards.card_type IS 'Tipo di carta (debit, credit)';
COMMENT ON COLUMN cards.card_status IS 'Stato della carta (active, flagged, blocked)';
COMMENT ON COLUMN cards.daily_limit IS 'Limite giornaliero di spesa della carta';

-- -----------------------------------------------------------------------------
-- Tabella: merchants (500 righe attese)
-- -----------------------------------------------------------------------------
CREATE TABLE merchants (
    merchant_id INTEGER PRIMARY KEY,
    merchant_name VARCHAR(50),
    category VARCHAR(30),
    country VARCHAR(50),
    risk_level VARCHAR(10) CHECK (risk_level IN ('low', 'medium', 'high'))
);

COMMENT ON TABLE merchants IS 'Tabella degli esercenti/commercianti (500 righe attese)';
COMMENT ON COLUMN merchants.merchant_id IS 'Identificativo univoco dell esercente (Primary Key)';
COMMENT ON COLUMN merchants.merchant_name IS 'Nome dell esercente';
COMMENT ON COLUMN merchants.category IS 'Categoria commerciale dell esercente';
COMMENT ON COLUMN merchants.country IS 'Paese dell esercente';
COMMENT ON COLUMN merchants.risk_level IS 'Livello di rischio dell esercente (low, medium, high)';

-- -----------------------------------------------------------------------------
-- Tabella: transactions (fino a 100000 righe)
-- -----------------------------------------------------------------------------
CREATE TABLE transactions (
    transaction_id BIGINT PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(customer_id),
    card_id INTEGER REFERENCES cards(card_id),
    merchant_id INTEGER REFERENCES merchants(merchant_id),
    amount NUMERIC(10,2),
    currency VARCHAR(3),
    country VARCHAR(50),
    transaction_time TIMESTAMP,
    channel VARCHAR(10) CHECK (channel IN ('online', 'pos', 'atm')),
    device_id VARCHAR(50),
    is_foreign_country BOOLEAN,
    is_night_transaction BOOLEAN,
    risk_score INTEGER,
    status VARCHAR(10) CHECK (status IN ('APPROVED', 'REVIEW', 'BLOCKED')),
    fraud_label BOOLEAN
);

COMMENT ON TABLE transactions IS 'Tabella delle transazioni (fino a 100000 righe)';
COMMENT ON COLUMN transactions.transaction_id IS 'Identificativo univoco della transazione (Primary Key)';
COMMENT ON COLUMN transactions.customer_id IS 'Riferimento al cliente (Foreign Key -> customers)';
COMMENT ON COLUMN transactions.card_id IS 'Riferimento alla carta (Foreign Key -> cards)';
COMMENT ON COLUMN transactions.merchant_id IS 'Riferimento all esercente (Foreign Key -> merchants)';
COMMENT ON COLUMN transactions.amount IS 'Importo della transazione';
COMMENT ON COLUMN transactions.currency IS 'Codice valuta (es. EUR, USD)';
COMMENT ON COLUMN transactions.country IS 'Paese di esecuzione della transazione';
COMMENT ON COLUMN transactions.transaction_time IS 'Data e ora della transazione';
COMMENT ON COLUMN transactions.channel IS 'Canale della transazione (online, pos, atm)';
COMMENT ON COLUMN transactions.device_id IS 'Identificativo del dispositivo';
COMMENT ON COLUMN transactions.is_foreign_country IS 'Indicatore transazione in paese estero';
COMMENT ON COLUMN transactions.is_night_transaction IS 'Indicatore transazione notturna';
COMMENT ON COLUMN transactions.risk_score IS 'Punteggio di rischio assegnato dal risk engine';
COMMENT ON COLUMN transactions.status IS 'Stato transazione (APPROVED, REVIEW, BLOCKED)';
COMMENT ON COLUMN transactions.fraud_label IS 'Etichetta di frode reale / Ground truth';

-- -----------------------------------------------------------------------------
-- Tabella: alerts (una riga per transazione con status REVIEW o BLOCKED)
-- -----------------------------------------------------------------------------
CREATE TABLE alerts (
    alert_id BIGINT PRIMARY KEY,
    transaction_id BIGINT REFERENCES transactions(transaction_id),
    customer_id INTEGER REFERENCES customers(customer_id),
    reason VARCHAR(200),
    risk_score INTEGER,
    created_at TIMESTAMP
);

COMMENT ON TABLE alerts IS 'Tabella degli alert per transazioni in REVIEW o BLOCKED';
COMMENT ON COLUMN alerts.alert_id IS 'Identificativo univoco dell alert (Primary Key)';
COMMENT ON COLUMN alerts.transaction_id IS 'Riferimento alla transazione (Foreign Key -> transactions)';
COMMENT ON COLUMN alerts.customer_id IS 'Riferimento al cliente (Foreign Key -> customers)';
COMMENT ON COLUMN alerts.reason IS 'Motivazione della generazione dell alert';
COMMENT ON COLUMN alerts.risk_score IS 'Punteggio di rischio associato';
COMMENT ON COLUMN alerts.created_at IS 'Data e ora di creazione dell alert';

-- -----------------------------------------------------------------------------
-- Indici su customer_id per query del Risk Engine
-- -----------------------------------------------------------------------------
CREATE INDEX idx_transactions_customer_id ON transactions(customer_id);
CREATE INDEX idx_alerts_customer_id ON alerts(customer_id);
