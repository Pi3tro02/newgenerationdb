# Client VoltDB

import argparse
import csv
from datetime import datetime
import json
import sys
import time 
import urllib.parse
import urllib.request
from typing import Any, Dict, List

def call_voltdb(api_url: str, procedure: str, parameters: list) -> dict:
    payload = urllib.parse.urlencode({
        "Procedure": procedure,
        "Parameters": json.dumps(parameters)
    }).encode("utf-8")

    req = urllib.request.Request(api_url, data=payload, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"Errore connessione VoltDB: {e}") from e

    if data.get("status") != 1:
        raise RuntimeError(f"Errore VoltDB: {data}")

    return data

def normalize_row(row: dict) -> dict:
    return {str(k).lower(): v for k, v in row.items()}

def extract_rows(response: dict) -> List[Dict[str, Any]]:
    results = response.get("results")

    if not results:
        return []

    # Formato possibile: {"results": {"0": [{"COL": value}]}}
    if isinstance(results, dict):
        first_table = results.get("0")
        if isinstance(first_table, list):
            return [normalize_row(row) for row in first_table]

    # Formato possibile: {"results": [{"schema": [...], "data": [[...]]}]}
    if isinstance(results, list) and results:
        table = results[0]

        if isinstance(table, dict) and "data" in table:
            schema = table.get("schema", [])
            data = table.get("data", [])

            column_names = []
            for col in schema:
                if isinstance(col, dict):
                    column_names.append(
                        col.get("name")
                        or col.get("columnName")
                        or col.get("column")
                    )
            
            rows = []
            for values in data:
                row = {
                    str(column_names[i]).lower(): values[i]
                    for i in range(min(len(column_names), len(values)))
                }
                rows.append(row)

            return rows
    return []

def fetch_one(api_url: str, sql: str, params: list) -> dict | None:
    response = call_voltdb(api_url, "@AdHoc", [sql, *params])
    rows = extract_rows(response)
    return rows[0] if rows else None

def fetch_content(api_url: str, customer_id: int, card_id: int, merchant_id: int) -> dict:
    customer = fetch_one(
        api_url,
        """
        SELECT home_country, risk_profile, avg_transaction_amount
        FROM customers
        WHERE customer_id = ?;
        """,
        [customer_id]
    )

    card = fetch_one(
        api_url,
        """
        SELECT card_status
        FROM cards
        WHERE card_id = ?;
        """,
        [card_id]
    )

    merchant = fetch_one(
        api_url,
        """
        SELECT risk_level
        FROM merchants
        WHERE merchant_id = ?;
        """,
        [merchant_id]
    )

    return {
        "customer": {
            "home_country": customer.get("home_country", "Italy") if customer else "Italy",
            "risk_profile": customer.get("risk_profile", "low") if customer else "low",
            "avg_transaction_amount": float(customer.get("avg_transaction_amount", 100.0)) if customer else 100.0,
        },
        "card": {
            "card_status": card.get("card_status", "active") if card else "active",
        },
        "merchant": {
            "risk_level": merchant.get("risk_level", "low") if merchant else "low",
        }
    }

import os
import sys

# Assicura la raggiungibilità del modulo `services.common` nel sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_services_dir = os.path.abspath(os.path.join(_current_dir, "../.."))
_workspace_root = os.path.abspath(os.path.join(_services_dir, ".."))
for _p in [_workspace_root, _services_dir]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from services.common.risk_engine import evaluate_transaction, build_alert_reason
except ImportError:
    from common.risk_engine import evaluate_transaction, build_alert_reason


def process_transaction(api_url: str, transaction: dict) -> dict:
    transaction_id = int(transaction["transaction_id"])
    customer_id = int(transaction["customer_id"])
    card_id = int(transaction["card_id"])
    merchant_id = int(transaction["merchant_id"])

    amount = float(transaction["amount"])
    currency = transaction.get("currency", "EUR")
    country = transaction["country"]
    transaction_time = transaction["transaction_time"]
    channel = transaction.get("channel", "pos")
    device_id = transaction.get("device_id", "")

    fraud_label = int(transaction.get("fraud_label", 0))

    context = fetch_content(api_url, customer_id, card_id, merchant_id)

    eval_result = evaluate_transaction(
        {
            "amount": amount,
            "country": country,
            "transaction_time": transaction_time,
            "channel": channel,
            "device_id": device_id,
        },
        context["customer"],
        context["card"],
        context["merchant"]
    )

    is_foreign = 1 if eval_result["is_foreign_country"] else 0
    is_night = 1 if eval_result["is_night_transaction"] else 0
    risk_score = int(eval_result["risk_score"])
    status = eval_result["status"]

    call_voltdb(
        api_url,
        "@AdHoc",
        [
            """
            INSERT INTO transactions (
                transaction_id, customer_id, card_id, merchant_id, amount,
                currency, country, transaction_time, channel, device_id,
                is_foreign_country, is_night_transaction, risk_score, status, fraud_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            transaction_id, customer_id, card_id, merchant_id, amount,
            currency, country, transaction_time, channel, device_id,
            is_foreign, is_night, risk_score, status, fraud_label
        ]
    )

    if status != "APPROVED":
        is_high_amount = amount > context["customer"]["avg_transaction_amount"] * 5
        reason = build_alert_reason(is_high_amount, bool(is_night), bool(is_foreign))

        call_voltdb(
            api_url,
            "@AdHoc",
            [
                """
                INSERT INTO alerts (
                    alert_id, transaction_id, customer_id, reason, risk_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                transaction_id, transaction_id, customer_id, reason, risk_score, transaction_time
            ]
        )

    return {
        "transaction_id": transaction_id,
        **eval_result
    }

def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0

    sorted_values = sorted(values)
    index = int(round((pct / 100.0) * (len(sorted_values) - 1)))
    return sorted_values[index]

def main():
    parser = argparse.ArgumentParser(description="Client VoltDB Fraud Detection Benchmark")
    parser.add_argument("--api-url", default="http://localhost:8080/api/2.0/", help="URL JSON API VoltDB")
    parser.add_argument("--transactions-csv", default="transactions.csv", help="Percorso CSV transazioni")
    parser.add_argument("--limit", type=int, default=0, help="Numero massimo transazioni, 0 = tutte")

    args = parser.parse_args()

    latencies_ms = []
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
                process_transaction(args.api_url, row)
                t1 = time.perf_counter()

                latencies_ms.append((t1 - t0) * 1000.0)
                processed_count += 1
    
    except KeyboardInterrupt:
        print("\nElaborazione interrotta dall'utente.")
    except Exception as e:
        print(f"[ERRORE] {e}", file=sys.stderr)
        sys.exit(1)

    total_time = time.perf_counter() - start_total
    throughput = processed_count / total_time if total_time > 0 else 0.0

    print("\n==================================================")
    print(" RISULTATI BENCHMARK VOLTDB ENGINE")
    print("==================================================")
    print(f"Transazioni elaborate : {processed_count}")
    print(f"Tempo totale (s)       : {total_time:.2f} s")
    print(f"Throughput             : {throughput:.2f} op/s")
    print(f"Latenza Media (ms)     : {(sum(latencies_ms) / len(latencies_ms)):.3f} ms" if latencies_ms else "Latenza Media (ms)     : 0.000 ms")
    print(f"Latenza P50 (ms)       : {percentile(latencies_ms, 50):.3f} ms")
    print(f"Latenza P95 (ms)       : {percentile(latencies_ms, 95):.3f} ms")
    print(f"Latenza P99 (ms)       : {percentile(latencies_ms, 99):.3f} ms")
    print("==================================================")

if __name__ == "__main__":
    main()
