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
from datetime import datetime
import os
import sys
import urllib.parse
import urllib.request
import time
from typing import Dict, List, Any


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

    context = fetch_content(
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
