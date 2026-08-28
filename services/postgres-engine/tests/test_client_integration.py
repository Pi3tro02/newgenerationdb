"""
Test di integrazione per il client PostgreSQL (client.py).
Esegue le verifiche su un database PostgreSQL reale.
Se il database non è disponibile, i test vengono automaticamente saltati con skipif.
"""

import os
import sys
import pytest

# Aggiunge il percorso del modulo 'app' al sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../app")))

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None

from client import fetch_context, process_transaction


TEST_DSN = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://fraud:fraud@localhost:5432/frauddb"
)


def is_postgres_available() -> bool:
    """
    Verifica se la connessione al database PostgreSQL di test è disponibile.
    """
    if psycopg2 is None:
        return False
    try:
        conn = psycopg2.connect(TEST_DSN, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not is_postgres_available(),
    reason="Impossibile connettersi al database PostgreSQL di test. Avvia prima il database con 'docker compose up postgres'"
)


@pytest.fixture
def db_conn():
    """
    Fixture pytest per il database di test.
    Ripulisce le tabelle ed inserisce i dati di test prima di ogni esecuzione.
    """
    conn = psycopg2.connect(TEST_DSN)

    with conn.cursor() as cur:
        # Pulizia preventiva delle tabelle
        cur.execute("TRUNCATE customers, cards, merchants, transactions, alerts CASCADE;")

        # Inserimento dati fixture minimi
        cur.execute(
            """
            INSERT INTO customers (customer_id, name, home_country, risk_profile, avg_transaction_amount, created_at)
            VALUES (1, 'Test Customer', 'Italy', 'low', 100.00, NOW());

            INSERT INTO cards (card_id, customer_id, card_type, card_status, daily_limit)
            VALUES (101, 1, 'debit', 'active', 1000);

            INSERT INTO cards (card_id, customer_id, card_type, card_status, daily_limit)
            VALUES (102, 1, 'credit', 'flagged', 2000);

            INSERT INTO merchants (merchant_id, merchant_name, category, country, risk_level)
            VALUES (501, 'Test Merchant', 'grocery', 'Italy', 'low');
            """
        )
    conn.commit()

    yield conn

    conn.close()


def test_fetch_context_returns_expected_fields(db_conn):
    """
    1. Verifica che fetch_context ritorni i valori esatti inseriti nella fixture.
    """
    context = fetch_context(db_conn, customer_id=1, card_id=101, merchant_id=501)

    assert context["customer"]["home_country"] == "Italy"
    assert context["customer"]["risk_profile"] == "low"
    assert context["customer"]["avg_transaction_amount"] == 100.0
    assert context["card"]["card_status"] == "active"
    assert context["merchant"]["risk_level"] == "low"


def test_fetch_context_missing_card_uses_default(db_conn):
    """
    2. Carta inesistente -> card_status default 'active', nessuna eccezione.
    """
    context = fetch_context(db_conn, customer_id=1, card_id=99999, merchant_id=501)

    assert context["card"]["card_status"] == "active"
    assert context["customer"]["home_country"] == "Italy"


def test_process_transaction_approved_writes_only_transaction(db_conn):
    """
    3. Transazione APPROVED: inserisce solo la riga in transactions e non in alerts.
    """
    transaction = {
        "transaction_id": 10001,
        "customer_id": 1,
        "card_id": 101,
        "merchant_id": 501,
        "amount": 50.0,
        "currency": "EUR",
        "country": "Italy",
        "transaction_time": "2026-05-01 12:00:00",
        "channel": "pos",
        "device_id": "DEV_001",
        "fraud_label": 0
    }

    result = process_transaction(db_conn, transaction)

    assert result["status"] == "APPROVED"
    assert result["transaction_id"] == 10001

    with db_conn.cursor() as cur:
        # Verifica presenza in transactions
        cur.execute("SELECT COUNT(*) FROM transactions WHERE transaction_id = %s;", (10001,))
        tx_count = cur.fetchone()[0]
        assert tx_count == 1

        # Verifica assenza in alerts
        cur.execute("SELECT COUNT(*) FROM alerts WHERE transaction_id = %s;", (10001,))
        alert_count = cur.fetchone()[0]
        assert alert_count == 0


def test_process_transaction_blocked_creates_alert(db_conn):
    """
    4. Transazione BLOCKED (risk_score >= 70): inserisce sia in transactions sia in alerts.
    """
    transaction = {
        "transaction_id": 10002,
        "customer_id": 1,
        "card_id": 102,  # card_status='flagged' (+40)
        "merchant_id": 501,
        "amount": 600.0,  # importo > 5 * 100 (+30) -> totale 70 (BLOCKED)
        "currency": "EUR",
        "country": "France",  # estero (+20)
        "transaction_time": "2026-05-01 02:00:00",  # notte (+10)
        "channel": "online",
        "device_id": "DEV_NEW_123",
        "fraud_label": 1
    }

    result = process_transaction(db_conn, transaction)

    assert result["status"] == "BLOCKED"
    assert result["risk_score"] >= 70

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Verifica inserimento in transactions
        cur.execute("SELECT COUNT(*) FROM transactions WHERE transaction_id = %s;", (10002,))
        tx_count = cur.fetchone()["count"]
        assert tx_count == 1

        # Verifica inserimento in alerts
        cur.execute("SELECT risk_score, reason, customer_id FROM alerts WHERE transaction_id = %s;", (10002,))
        alert = cur.fetchone()
        assert alert is not None
        assert alert["risk_score"] == result["risk_score"]
        assert alert["customer_id"] == 1
        assert "high_amount" in alert["reason"]
