"""
VoltDB client.

ResponsabilitÃ :
- comunicare con VoltDB tramite JSON API;
- recuperare il contesto necessario per una transazione;
- applicare il risk engine comune;
- inserire transactions;
- inserire alerts.

La lettura di transactions.csv, il rate limiting e il benchmark
sono responsabilitÃ  del simulator.
"""
import json
import argparse
import csv
import os
import sys
import urllib.parse
import urllib.request
import time
from typing import Dict, List, Any, Optional


# ---------------------------------------------------------------------------
# Import risk engine comune
# ---------------------------------------------------------------------------

_CURRENT_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

_SERVICES_DIR = os.path.abspath(
    os.path.join(_CURRENT_DIR, "../..")
)

_WORKSPACE_ROOT = os.path.abspath(
    os.path.join(_SERVICES_DIR, "..")
)

if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from services.common.risk_engine import (
    evaluate_transaction,
    build_alert_reason,
)

# ---------------------------------------------------------------------------
# VoltDB communication
# ---------------------------------------------------------------------------


def call_voltdb(
    api_url: str,
    procedure: str,
    parameters: list,
) -> dict:
    """
    Esegue una chiamata alla JSON API di VoltDB.

    Args:
        api_url:
            Endpoint JSON API VoltDB.

        procedure:
            Procedura VoltDB, ad esempio @AdHoc.

        parameters:
            Parametri della procedura.

    Returns:
        Risposta JSON decodificata.

    Raises:
        RuntimeError:
            In caso di errore HTTP, JSON o VoltDB.
    """

    payload = urllib.parse.urlencode(
        {
            "Procedure": procedure,
            "Parameters": json.dumps(
                parameters
            ),
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        api_url,
        data=payload,
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:
            raw_data = response.read().decode(
                "utf-8"
            )

            data = json.loads(raw_data)

    except Exception as exc:
        raise RuntimeError(
            f"Errore connessione VoltDB: {exc}"
        ) from exc

    if data.get("status") != 1:
        raise RuntimeError(
            f"Errore VoltDB: {data}"
        )

    return data


# ---------------------------------------------------------------------------
# Result parsing
# ---------------------------------------------------------------------------


def normalize_row(row: dict) -> dict:
    """
    Normalizza i nomi delle colonne in lowercase.
    """

    return {
        str(key).lower(): value
        for key, value in row.items()
    }


def extract_rows(
    response: dict,
) -> List[Dict[str, Any]]:
    """
    Estrae le righe da diversi formati di risposta
    possibili della JSON API VoltDB.
    """

    results = response.get("results")

    if not results:
        return []

    # ---------------------------------------------------------------
    # Formato:
    #
    # {
    #   "results": {
    #       "0": [
    #           {"COL": value}
    #       ]
    #   }
    # }
    # ---------------------------------------------------------------

    if isinstance(results, dict):
        first_table = results.get("0")

        if isinstance(first_table, list):
            return [
                normalize_row(row)
                for row in first_table
            ]

    # ---------------------------------------------------------------
    # Formato:
    #
    # {
    #   "results": [
    #       {
    #           "schema": [...],
    #           "data": [...]
    #       }
    #   ]
    # }
    # ---------------------------------------------------------------

    if isinstance(results, list) and results:
        table = results[0]

        if (
            isinstance(table, dict)
            and "data" in table
        ):
            schema = table.get(
                "schema",
                [],
            )

            data = table.get(
                "data",
                [],
            )

            column_names = []

            for column in schema:
                if isinstance(column, dict):
                    column_names.append(
                        column.get("name")
                        or column.get("columnName")
                        or column.get("column")
                    )

            rows = []

            for values in data:
                row = {
                    str(column_names[index]).lower():
                    values[index]
                    for index in range(
                        min(
                            len(column_names),
                            len(values),
                        )
                    )
                }

                rows.append(row)

            return rows

    return []


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------


def fetch_one(
    api_url: str,
    sql: str,
    params: list,
) -> Optional[dict]:
    """
    Esegue una SELECT e restituisce la prima riga.
    """

    response = call_voltdb(
        api_url,
        "@AdHoc",
        [
            sql,
            *params,
        ],
    )

    rows = extract_rows(response)

    return rows[0] if rows else None


def fetch_content(
    api_url: str,
    customer_id: int,
    card_id: int,
    merchant_id: int,
) -> dict:
    """
    Recupera dal database il contesto necessario
    al risk engine.
    """

    customer = fetch_one(
        api_url,
        """
        SELECT
            home_country,
            risk_profile,
            avg_transaction_amount
        FROM customers
        WHERE customer_id = ?;
        """,
        [customer_id],
    )

    card = fetch_one(
        api_url,
        """
        SELECT
            card_status
        FROM cards
        WHERE card_id = ?;
        """,
        [card_id],
    )

    merchant = fetch_one(
        api_url,
        """
        SELECT
            risk_level
        FROM merchants
        WHERE merchant_id = ?;
        """,
        [merchant_id],
    )

    return {
        "customer": {
            "home_country": (
                customer.get(
                    "home_country",
                    "Italy",
                )
                if customer
                else "Italy"
            ),
            "risk_profile": (
                customer.get(
                    "risk_profile",
                    "low",
                )
                if customer
                else "low"
            ),
            "avg_transaction_amount": (
                float(
                    customer.get(
                        "avg_transaction_amount",
                        100.0,
                    )
                )
                if customer
                else 100.0
            ),
        },
        "card": {
            "card_status": (
                card.get(
                    "card_status",
                    "active",
                )
                if card
                else "active"
            ),
        },
        "merchant": {
            "risk_level": (
                merchant.get(
                    "risk_level",
                    "low",
                )
                if merchant
                else "low"
            ),
        },
    }

_CONTEXT_CACHE = None

def fetch_all(
    api_url: str,
    sql: str,
    params: Optional[list] = None,
) -> List[Dict[str, Any]]:
    """ 
    Esegue una SELECT e restituisce tutte le righe. 
    Usata per caricare in memoria le tabelle anagrafiche relativamente statiche: customers, cards e merchants
    """

    response = call_voltdb(
        api_url,
        "@AdHoc",
        [
            sql,
            *(params or []),
        ],
    )

    return extract_rows(response)

def load_context_cache(api_url: str) -> dict:
    """
    Carica cusomers, cards e merchants in memoria.
    """

    customer_rows = fetch_all(
        api_url,
        """
        SELECT
            customer_id,
            home_country,
            risk_profile,
            avg_transaction_amount
        FROM customers;
        """,
    )

    card_rows = fetch_all(
        api_url,
        """
        SELECT 
            card_id,
            card_status
        FROM cards;
        """,
    )

    merchant_rows = fetch_all(
        api_url,
        """
        SELECT
            merchant_id,
            risk_level
        FROM merchants;
        """,
    )

    customers = {
        int(row["customer_id"]): {
            "home_country": row.get("home_country", "Italy"),
            "risk_profile": row.get("risk_profile", "low"),
            "avg_transaction_amount": float(
                row.get("avg_transaction_amount", 100.0)
            ),
        }
        for row in customer_rows
    }

    cards = {
        int(row["card_id"]): {
            "card_status": row.get("card_status", "active"),
        }
        for row in card_rows
    }

    merchants = {
        int(row["merchant_id"]): {
            "risk_level": row.get("risk_level", "low"),
        }
        for row in merchant_rows
    }

    return {
        "customers": customers,
        "cards": cards,
        "merchants": merchants
    }

def initialize_cache(api_url: str) -> dict:
    """
    Inizializza la cache globale del client VoltDB.
    Restituisce i conteggi caricati.
    """

    global _CONTEXT_CACHE

    _CONTEXT_CACHE = load_context_cache(api_url)

    return {
        "customers": len(_CONTEXT_CACHE["customers"]),
        "cards": len(_CONTEXT_CACHE["cards"]),
        "merchants": len(_CONTEXT_CACHE["merchants"])
    }

def clear_cache() -> None:
    """
    Metodo che svuota la cache globale.
    """

    global _CONTEXT_CACHE
    _CONTEXT_CACHE = None

def fetch_content_cached_or_db(
    api_url: str,
    customer_id: int,
    card_id: int,
    merchant_id: int
) -> dict:
    """
    Metodo che recupera il contesto della cache, se disponibile.
    Se la cache non è stata inizializzata, usa il percorso base con query verso VoltDB.
    """

    if _CONTEXT_CACHE is None:
        return fetch_content(
            api_url,
            customer_id,
            card_id,
            merchant_id
        )
    
    customer = _CONTEXT_CACHE["customers"].get(
        customer_id,
        {
            "home_country": "Italy",
            "risk_profile": "low",
            "avg_transaction_amount": 100.0
        },
    )

    card = _CONTEXT_CACHE["cards"].get(
        card_id,
        {
            "card_status": "active",
        },
    )

    merchant = _CONTEXT_CACHE["merchants"].get(
        merchant_id,
        {
            "risk_level": "low",
        },
    )

    return {
        "customer": customer,
        "card": card,
        "merchant": merchant
    }

# ---------------------------------------------------------------------------
# Transaction processing
# ---------------------------------------------------------------------------


def process_transaction(
    api_url: str,
    transaction: dict,
) -> dict:
    """
    Elabora una singola transazione.

    Questa funzione rappresenta l'interfaccia utilizzata
    dal transaction simulator.

    Non legge il CSV e non misura il benchmark.
    """

    transaction_id = int(
        transaction["transaction_id"]
    )

    customer_id = int(
        transaction["customer_id"]
    )

    card_id = int(
        transaction["card_id"]
    )

    merchant_id = int(
        transaction["merchant_id"]
    )

    amount = float(
        transaction["amount"]
    )

    currency = transaction.get(
        "currency",
        "EUR",
    )

    country = transaction["country"]

    transaction_time = transaction[
        "transaction_time"
    ]

    channel = transaction.get(
        "channel",
        "pos",
    )

    device_id = transaction.get(
        "device_id",
        "",
    )

    # Il valore fraud_label viene dal CSV.
    #
    # Non viene utilizzato dal risk engine per decidere
    # il risk_score/status.
    #
    # Serve come ground truth sperimentale.
    fraud_label = int(
        transaction.get(
            "fraud_label",
            0,
        )
    )

    # ---------------------------------------------------------------
    # Recupero contesto
    # ---------------------------------------------------------------

    context = fetch_content_cached_or_db(
        api_url,
        customer_id,
        card_id,
        merchant_id,
    )

    # ---------------------------------------------------------------
    # Risk engine comune
    # ---------------------------------------------------------------

    evaluation = evaluate_transaction(
        {
            "amount": amount,
            "country": country,
            "transaction_time": transaction_time,
            "channel": channel,
            "device_id": device_id,
        },
        context["customer"],
        context["card"],
        context["merchant"],
    )

    is_foreign = int(
        bool(
            evaluation[
                "is_foreign_country"
            ]
        )
    )

    is_night = int(
        bool(
            evaluation[
                "is_night_transaction"
            ]
        )
    )

    risk_score = int(
        evaluation["risk_score"]
    )

    status = evaluation["status"]

    # ---------------------------------------------------------------
    # INSERT transaction
    # ---------------------------------------------------------------

    call_voltdb(
        api_url,
        "@AdHoc",
        [
            """
            INSERT INTO transactions (
                transaction_id,
                customer_id,
                card_id,
                merchant_id,
                amount,
                currency,
                country,
                transaction_time,
                channel,
                device_id,
                is_foreign_country,
                is_night_transaction,
                risk_score,
                status,
                fraud_label
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?
            );
            """,
            transaction_id,
            customer_id,
            card_id,
            merchant_id,
            amount,
            currency,
            country,
            transaction_time,
            channel,
            device_id,
            is_foreign,
            is_night,
            risk_score,
            status,
            fraud_label,
        ],
    )

    # ---------------------------------------------------------------
    # INSERT alert
    # ---------------------------------------------------------------

    if status != "APPROVED":
        is_high_amount = (
            amount
            > context["customer"][
                "avg_transaction_amount"
            ] * 5
        )

        reason = build_alert_reason(
            is_high_amount,
            bool(is_night),
            bool(is_foreign),
        )

        call_voltdb(
            api_url,
            "@AdHoc",
            [
                """
                INSERT INTO alerts (
                    alert_id,
                    transaction_id,
                    customer_id,
                    reason,
                    risk_score,
                    created_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?
                );
                """,
                transaction_id,
                transaction_id,
                customer_id,
                reason,
                risk_score,
                transaction_time,
            ],
        )

    # ---------------------------------------------------------------
    # Risultato
    # ---------------------------------------------------------------

    return {
        "transaction_id": transaction_id,
        "risk_score": risk_score,
        "status": status,
        "is_foreign_country": is_foreign,
        "is_night_transaction": is_night,
        "fraud_label": fraud_label,
    }


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0

    sorted_values = sorted(values)

    if len(sorted_values) == 1:
        return sorted_values[0]

    position = (len(sorted_values) - 1) * pct / 100.0
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower

    return sorted_values[lower] + (
        sorted_values[upper] - sorted_values[lower]
    ) * fraction


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Client VoltDB Fraud Detection"
    )
    parser.add_argument(
        "--voltdb-api-url",
        default="http://localhost:8080/api/2.0",
        help="Endpoint JSON API VoltDB",
    )
    parser.add_argument(
        "--transactions-csv",
        default="transactions.csv",
        help="Percorso file CSV transazioni",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Numero massimo transazioni (0 = tutte)",
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Precarica customers/cards/merchants in memoria",
    )

    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit deve essere >= 0")

    if args.use_cache:
        cache_info = initialize_cache(args.voltdb_api_url)
        print(
            "[INFO] Cache VoltDB inizializzata: "
            f"customers={cache_info['customers']}, "
            f"cards={cache_info['cards']}, "
            f"merchants={cache_info['merchants']}"
        )

    latencies_ms: List[float] = []
    processed_count = 0
    error_count = 0

    print(
        f"Inizio elaborazione transazioni da "
        f"'{args.transactions_csv}'..."
    )
    start_total = time.perf_counter()

    with open(args.transactions_csv, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            if args.limit > 0 and processed_count >= args.limit:
                break

            try:
                start = time.perf_counter()
                process_transaction(args.voltdb_api_url, row)
                end = time.perf_counter()

                latencies_ms.append((end - start) * 1000.0)
                processed_count += 1

            except Exception as exc:
                error_count += 1
                print(
                    f"[ERRORE] transaction_id="
                    f"{row.get('transaction_id', '?')}: {exc}",
                    file=sys.stderr,
                )

    total_time = time.perf_counter() - start_total

    if processed_count == 0:
        print("Nessuna transazione elaborata.")
        return 1 if error_count else 0

    throughput = processed_count / total_time if total_time > 0 else 0.0

    print("\n" + "=" * 50)
    print(" RISULTATI BENCHMARK VOLTDB ENGINE")
    print("=" * 50)
    print(f"Transazioni elaborate : {processed_count}")
    print(f"Errori                : {error_count}")
    print(f"Tempo totale (s)      : {total_time:.2f} s")
    print(f"Throughput            : {throughput:.2f} op/s")
    print(
        f"Latenza Media (ms)    : "
        f"{sum(latencies_ms) / len(latencies_ms):.3f} ms"
    )
    print(f"Latenza P50 (ms)      : {percentile(latencies_ms, 50):.3f} ms")
    print(f"Latenza P95 (ms)      : {percentile(latencies_ms, 95):.3f} ms")
    print(f"Latenza P99 (ms)      : {percentile(latencies_ms, 99):.3f} ms")
    print("=" * 50)

    return 1 if error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
