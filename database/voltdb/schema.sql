-- Schema VoltDB
DROP TABLE alerts IF EXISTS;
DROP TABLE transactions IF EXISTS;
DROP TABLE merchants IF EXISTS;
DROP TABLE cards IF EXISTS;
DROP TABLE customers IF EXISTS;

CREATE TABLE customers (
    customer_id INTEGER NOT NULL,
    name VARCHAR(50),
    home_country VARCHAR(50),
    risk_profile VARCHAR(10),
    avg_transaction_amount DECIMAL,
    created_at TIMESTAMP,
    PRIMARY KEY (customer_id)
);

CREATE TABLE cards (
    card_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    card_type VARCHAR(10),
    card_status VARCHAR(10),
    daily_limit INTEGER,
    PRIMARY KEY (card_id)
);

CREATE TABLE merchants (
    merchant_id INTEGER NOT NULL,
    merchant_name VARCHAR(50),
    category VARCHAR(30),
    country VARCHAR(50),
    risk_level VARCHAR(10),
    PRIMARY KEY (merchant_id)
);

CREATE TABLE transactions (
    transaction_id BIGINT NOT NULL,
    customer_id INTEGER NOT NULL,
    card_id INTEGER NOT NULL,
    merchant_id INTEGER NOT NULL,
    amount DECIMAL,
    currency VARCHAR(3),
    country VARCHAR(50),
    transaction_time TIMESTAMP,
    channel VARCHAR(10),
    device_id VARCHAR(50),
    is_foreign_country TINYINT,
    is_night_transaction TINYINT,
    risk_score INTEGER,
    status VARCHAR(10),
    fraud_label TINYINT,
    PRIMARY KEY (transaction_id)
);

CREATE TABLE alerts (
    alert_id BIGINT NOT NULL,
    transaction_id BIGINT NOT NULL,
    customer_id INTEGER NOT NULL,
    reason VARCHAR(200),
    risk_score INTEGER,
    created_at TIMESTAMP,
    PRIMARY KEY (alert_id)
);

PARTITION TABLE transactions ON COLUMN transaction_id;
PARTITION TABLE alerts ON COLUMN alert_id;
