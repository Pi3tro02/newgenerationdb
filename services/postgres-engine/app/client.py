"""
Client PostgreSQL per il sistema di rilevamento frodi.
Interfaccia con la base dati PostgreSQL tramite psycopg2 per il recupero del contesto,
la valutazione del rischio e la registrazione in tempo reale delle transazioni ed alert.
"""

import argparse
import csv
from datetime import datetime
import sys
import time
from typing import Dict, List, Any

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None

try:
    from .risk_engine import evaluate_transaction, build_alert_reason
except ImportError:
    from risk_engine import evaluate_transaction, build_alert_reason


def connect_db(dsn: str):
    """
    Apre una connessione verso la base dati PostgreSQL tramite psycopg2.
    Gestisce eventuali errori di connessione fornendo messaggi chiari.
    """
    if psycopg2 is None:
        print("[ERRORE] Il modulo 'psycopg2' non è installato nell'ambiente Python.", file=sys.stderr)
        sys.exit(1)

    try:
        conn = psycopg2.connect(dsn)
        return conn
    except Exception as e:
        print(f"[ERRORE CONN] Impossibile connettersi al database PostgreSQL con DSN: '{dsn}'.", file=sys.stderr)
        print(f"Dettaglio errore: {e}", file=sys.stderr)
        sys.exit(1)


def fetch_context(conn, customer_id: int, card_id: int, merchant_id: int) -> dict:
    """
    Esegue 3 query distinte per recuperare il contesto di cliente, carta ed esercente.
    In caso di carta o esercente non trovati, vengono applicati valori di default sicuri.
    """
    context = {
        "customer": {"home_country": "IT", "risk_profile": "low", "avg_transaction_amount": 100.0},
        "card": {"card_status": "active"},
        "merchant": {"risk_level": "low"}
    }

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 1. Query cliente
        cur.execute(
            """
            SELECT home_country, risk_profile, avg_transaction_amount
            FROM customers
            WHERE customer_id = %s
            """,
            (customer_id,)
        )
        row_cust = cur.fetchone()
        if row_cust:
            context["customer"] = {
                "home_country": row_cust["home_country"],
                "risk_profile": row_cust["risk_profile"],
                "avg_transaction_amount": float(row_cust["avg_transaction_amount"])
            }

        # 2. Query carta (default: card_status="active")
        cur.execute(
            """
            SELECT card_status
            FROM cards
            WHERE card_id = %s
            """,
            (card_id,)
        )
        row_card = cur.fetchone()
        if row_card:
            context["card"] = {
                "card_status": row_card["card_status"]
            }

        # 3. Query esercente (default: risk_level="low")
        cur.execute(
            """
            SELECT risk_level
            FROM merchants
            WHERE merchant_id = %s
            """,
            (merchant_id,)
        )
        row_merch = cur.fetchone()
        if row_merch:
            context["merchant"] = {
                "risk_level": row_merch["risk_level"]
            }

    return context


def process_transaction(conn, transaction: dict) -> dict:
    """
    Elabora una transazione:
    - Recupera il contesto dal DB tramite fetch_context.
    - Calcola lo stato ed il punteggio di rischio con evaluate_transaction.
    - Inserisce la riga in `transactions` (query parametrizzata).
    - Se lo stato è diverso da 'APPROVED', inserisce una riga in `alerts`.
    - Esegue il commit della transazione.
    - Ritorna il risultato di evaluate_transaction con l'aggiunta di transaction_id.
    """
    customer_id = int(transaction["customer_id"])
    card_id = int(transaction["card_id"])
    merchant_id = int(transaction["merchant_id"])

    # Conversione data/ora se in formato stringa
    tx_time = transaction["transaction_time"]
    if isinstance(tx_time, str):
        tx_time_dt = datetime.strptime(tx_time, "%Y-%m-%d %H:%M:%S")
    else:
        tx_time_dt = tx_time

    # 1. Recupero contesto
    context = fetch_context(conn, customer_id, card_id, merchant_id)

    # 2. Valutazione rischio
    engine_input = {
        "amount": float(transaction["amount"]),
        "country": transaction["country"],
        "transaction_time": tx_time_dt,
        "channel": transaction.get("channel", "pos"),
        "device_id": transaction.get("device_id", "")
    }

    eval_result = evaluate_transaction(
        engine_input,
        context["customer"],
        context["card"],
        context["merchant"]
    )

    status = eval_result["status"]
    risk_score = eval_result["risk_score"]
    is_foreign = eval_result["is_foreign_country"]
    is_night = eval_result["is_night_transaction"]

    transaction_id = int(transaction["transaction_id"])
    amount = float(transaction["amount"])
    currency = transaction.get("currency", "EUR")
    country = transaction["country"]
    channel = transaction.get("channel", "pos")
    device_id = transaction.get("device_id", "")

    # Parsing di fraud_label
    raw_fraud = transaction.get("fraud_label", 0)
    fraud_label = bool(int(raw_fraud)) if str(raw_fraud).isdigit() else bool(raw_fraud)

    with conn.cursor() as cur:
        # 3. Inserimento in transactions
        cur.execute(
            """
            INSERT INTO transactions (
                transaction_id, customer_id, card_id, merchant_id, amount,
                currency, country, transaction_time, channel, device_id,
                is_foreign_country, is_night_transaction, risk_score, status, fraud_label
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            """,
            (
                transaction_id, customer_id, card_id, merchant_id, amount,
                currency, country, tx_time_dt, channel, device_id,
                is_foreign, is_night, risk_score, status, fraud_label
            )
        )

        # 4. Inserimento in alerts se status != 'APPROVED'
        if status != "APPROVED":
            is_high_amount = amount > context["customer"]["avg_transaction_amount"] * 5
            reason = build_alert_reason(is_high_amount, is_night, is_foreign)
            cur.execute(
                """
                INSERT INTO alerts (
                    alert_id, transaction_id, customer_id, reason, risk_score, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    transaction_id, transaction_id, customer_id, reason, risk_score, tx_time_dt
                )
            )

    # 5. Commit
    conn.commit()

    return {
        "transaction_id": transaction_id,
        **eval_result
    }


def main():
    parser = argparse.ArgumentParser(description="Client PostgreSQL Fraud Detection Benchmark")
    parser.add_argument("--dsn", type=str, default="postgresql://fraud:fraud@localhost:5432/frauddb", help="DSN di connessione PostgreSQL")
    parser.add_argument("--transactions-csv", type=str, default="transactions.csv", help="Percorso file CSV transazioni")
    parser.add_argument("--limit", type=int, default=0, help="Numero massimo transazioni (0 = tutte)")

    args = parser.parse_args()

    conn = connect_db(args.dsn)

    latencies_ms: List[float] = []
    processed_count = 0

    print(f"Inizio elaborazione transazioni da '{args.transactions_csv}'...")
    start_total = time.perf_counter()

    try:
        with open(args.transactions_csv, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if args.limit > 0 and processed_count >= args.limit:
                    break

                t0 = time.perf_counter()
                process_transaction(conn, row)
                t1 = time.perf_counter()

                latencies_ms.append((t1 - t0) * 1000.0)
                processed_count += 1
    except KeyboardInterrupt:
        print("\nElaborazione interrotta dall'utente.")
    finally:
        conn.close()

    total_time = time.perf_counter() - start_total

    if processed_count == 0:
        print("Nessuna transazione elaborata.")
        return

    throughput = processed_count / total_time
    avg_latency = sum(latencies_ms) / processed_count

    latencies_sorted = sorted(latencies_ms)
    p50 = latencies_sorted[int(len(latencies_sorted) * 0.50)]
    p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
    p99 = latencies_sorted[int(len(latencies_sorted) * 0.99)]

    print("\n" + "=" * 50)
    print(" RISULTATI BENCHMARK POSTGRESQL ENGINE")
    print("=" * 50)
    print(f"Transazioni elaborate : {processed_count}")
    print(f"Tempo totale (s)       : {total_time:.2f} s")
    print(f"Throughput             : {throughput:.2f} op/s")
    print(f"Latenza Media (ms)     : {avg_latency:.3f} ms")
    print(f"Latenza P50 (ms)       : {p50:.3f} ms")
    print(f"Latenza P95 (ms)       : {p95:.3f} ms")
    print(f"Latenza P99 (ms)       : {p99:.3f} ms")
    print("=" * 50)


if __name__ == "__main__":
    main()
