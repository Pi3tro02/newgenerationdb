"""
Transaction simulator.

Responsabilità:
- leggere transactions.csv tramite transaction_stream();
- selezionare il target PostgreSQL / VoltDB / both;
- inviare la stessa sequenza di transazioni ai database;
- misurare la latenza end-to-end per ogni target;
- verificare la parità PostgreSQL/VoltDB quando --target both.

Il simulatore non implementa le regole antifrode.
"""

import argparse
import importlib.util
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Path del progetto
# ---------------------------------------------------------------------------

CURRENT_DIR = Path(__file__).resolve().parent
SERVICES_DIR = CURRENT_DIR.parents[1]
WORKSPACE_ROOT = SERVICES_DIR.parent

for path in (WORKSPACE_ROOT, SERVICES_DIR):
    path_str = str(path)

    if path_str not in sys.path:
        sys.path.insert(0, path_str)


# ---------------------------------------------------------------------------
# Stream
# ---------------------------------------------------------------------------

from stream import transaction_stream


# ---------------------------------------------------------------------------
# Caricamento dinamico dei client
#
# I nomi delle directory contengono "-":
#
#   postgres-engine
#   voltdb-engine
#
# quindi non possiamo utilizzare direttamente:
#
#   from services.postgres-engine...
#
# Usiamo importlib.
# ---------------------------------------------------------------------------


def load_client_module(engine_directory: str):
    """
    Carica il client.py di uno specifico engine.
    """

    client_path = (
        SERVICES_DIR
        / engine_directory
        / "app"
        / "client.py"
    )

    if not client_path.exists():
        raise FileNotFoundError(
            f"Client non trovato: {client_path}"
        )

    module_name = f"{engine_directory.replace('-', '_')}_client"

    spec = importlib.util.spec_from_file_location(
        module_name,
        client_path,
    )

    if spec is None or spec.loader is None:
        raise ImportError(
            f"Impossibile caricare il client: {client_path}"
        )

    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    return module


# ---------------------------------------------------------------------------
# Configurazione target
# ---------------------------------------------------------------------------


class TargetConfig:
    def __init__(
        self,
        postgres_url: str,
        voltdb_url: str,
    ):
        self.postgres_url = postgres_url
        self.voltdb_url = voltdb_url


# ---------------------------------------------------------------------------
# Metriche
# ---------------------------------------------------------------------------


class TargetMetrics:
    def __init__(self):
        self.processed = 0
        self.errors = 0

        self.latencies_ms = []

        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def start(self):
        self.start_time = time.perf_counter()

    def finish(self):
        self.end_time = time.perf_counter()

    def add_success(self, latency_ms: float):
        self.processed += 1
        self.latencies_ms.append(latency_ms)

    def add_error(self):
        self.errors += 1

    @property
    def total_time(self) -> float:
        if self.start_time is None or self.end_time is None:
            return 0.0

        return self.end_time - self.start_time

    @property
    def throughput(self) -> float:
        if self.total_time <= 0:
            return 0.0

        return self.processed / self.total_time

    @property
    def average_latency(self) -> float:
        if not self.latencies_ms:
            return 0.0

        return sum(self.latencies_ms) / len(self.latencies_ms)

    @property
    def p50(self) -> float:
        return percentile(self.latencies_ms, 50)

    @property
    def p95(self) -> float:
        return percentile(self.latencies_ms, 95)

    @property
    def p99(self) -> float:
        return percentile(self.latencies_ms, 99)

    @property
    def max_latency(self) -> float:
        if not self.latencies_ms:
            return 0.0

        return max(self.latencies_ms)


def percentile(values, pct: float) -> float:
    """
    Calcola il percentile usando interpolazione lineare.

    Per il benchmark è preferibile evitare il precedente:
        int(round(...))
    perché può introdurre salti artificiali su dataset piccoli.
    """

    if not values:
        return 0.0

    sorted_values = sorted(values)

    if len(sorted_values) == 1:
        return float(sorted_values[0])

    position = (len(sorted_values) - 1) * (pct / 100.0)

    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)

    fraction = position - lower

    return (
        sorted_values[lower]
        + (sorted_values[upper] - sorted_values[lower]) * fraction
    )


# ---------------------------------------------------------------------------
# Normalizzazione risultati
# ---------------------------------------------------------------------------


def result_value(result: Dict[str, Any], key: str, default=None):
    """
    Recupera una proprietà dal risultato del client.

    Il metodo rende il simulatore tollerante rispetto a eventuali
    differenze minori tra il client PostgreSQL e quello VoltDB.
    """

    if result is None:
        return default

    return result.get(key, default)


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------


def process_postgres(
    postgres_client,
    transaction: Dict[str, str],
    postgres_url: str,
) -> Dict[str, Any]:
    """
    Elabora una singola transazione PostgreSQL.
    """

    return postgres_client.process_transaction(
        postgres_url,
        transaction,
    )


def process_voltdb(
    voltdb_client,
    transaction: Dict[str, str],
    voltdb_url: str,
) -> Dict[str, Any]:
    """
    Elabora una singola transazione VoltDB.
    """

    return voltdb_client.process_transaction(
        voltdb_url,
        transaction,
    )


# ---------------------------------------------------------------------------
# Parity check
# ---------------------------------------------------------------------------


def check_parity(
    transaction: Dict[str, str],
    postgres_result: Dict[str, Any],
    voltdb_result: Dict[str, Any],
) -> Optional[str]:
    """
    Controlla che PostgreSQL e VoltDB abbiano prodotto lo stesso
    risk_score e status.

    Restituisce None se tutto coincide.
    """

    transaction_id = transaction.get("transaction_id")

    pg_score = result_value(
        postgres_result,
        "risk_score",
    )

    vdb_score = result_value(
        voltdb_result,
        "risk_score",
    )

    pg_status = result_value(
        postgres_result,
        "status",
    )

    vdb_status = result_value(
        voltdb_result,
        "status",
    )

    differences = []

    if pg_score != vdb_score:
        differences.append(
            f"risk_score PG={pg_score} VoltDB={vdb_score}"
        )

    if pg_status != vdb_status:
        differences.append(
            f"status PG={pg_status} VoltDB={vdb_status}"
        )

    if differences:
        return (
            f"transaction_id={transaction_id}: "
            + "; ".join(differences)
        )

    return None


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Real-time transaction simulator "
            "per PostgreSQL e VoltDB."
        )
    )

    parser.add_argument(
        "--transactions-csv",
        default="transactions.csv",
        help="Percorso del file transactions.csv",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help=(
            "Numero massimo di transazioni. "
            "0 = tutte."
        ),
    )

    parser.add_argument(
        "--tps",
        type=float,
        default=None,
        help=(
            "Target Transactions Per Second. "
            "Se omesso, le transazioni vengono inviate "
            "senza rate limiting."
        ),
    )

    parser.add_argument(
        "--target",
        choices=("postgres", "voltdb", "both"),
        default="postgres",
        help="Database target.",
    )

    parser.add_argument(
        "--postgres-url",
        default="postgresql://fraud:fraud@localhost:5432/frauddb",
        help=(
            "Connection string PostgreSQL. "
            "Viene passata direttamente al client PostgreSQL."
        ),
    )

    parser.add_argument(
        "--voltdb-api-url",
        default="http://localhost:8080/api/2.0/",
        help="URL JSON API VoltDB.",
    )

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit deve essere >= 0")

    if args.tps is not None and args.tps <= 0:
        parser.error("--tps deve essere > 0")

    print("=" * 60)
    print(" TRANSACTION SIMULATOR")
    print("=" * 60)
    print(f"CSV       : {args.transactions_csv}")
    print(
        f"Limit     : "
        f"{args.limit if args.limit > 0 else 'tutte'}"
    )
    print(
        f"TPS       : "
        f"{args.tps if args.tps is not None else 'unlimited'}"
    )
    print(f"Target    : {args.target}")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Caricamento client
    # ------------------------------------------------------------------

    postgres_client = None
    postgres_conn = None
    voltdb_client = None

    try:
        if args.target in ("postgres", "both"):
            postgres_client = load_client_module(
                "postgres-engine"
            )
            postgres_conn = postgres_client.connect_db(
                args.postgres_url
            )

        if args.target in ("voltdb", "both"):
            voltdb_client = load_client_module(
                "voltdb-engine"
            )

    except Exception as exc:
        print(
            f"[ERRORE] Impossibile caricare un client: {exc}",
            file=sys.stderr,
        )
        return 1

    # ------------------------------------------------------------------
    # Metriche
    # ------------------------------------------------------------------

    postgres_metrics = TargetMetrics()
    voltdb_metrics = TargetMetrics()

    parity_errors = []

    processed_stream = 0

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    global_start = time.perf_counter()

    if args.target in ("postgres", "both"):
        postgres_metrics.start()

    if args.target in ("voltdb", "both"):
        voltdb_metrics.start()

    try:
        for transaction in transaction_stream(
            csv_path=args.transactions_csv,
            limit=args.limit,
            tps=args.tps,
        ):
            processed_stream += 1

            transaction_id = transaction.get(
                "transaction_id",
                "?",
            )

            print(
                f"[{processed_stream}] "
                f"transaction_id={transaction_id}",
                end="",
                flush=True,
            )

            postgres_result = None
            voltdb_result = None

            # ----------------------------------------------------------
            # PostgreSQL
            # ----------------------------------------------------------

            if args.target in ("postgres", "both"):
                try:
                    start = time.perf_counter()

                    postgres_result = process_postgres(
                        postgres_client,
                        transaction,
                        postgres_conn,
                    )

                    end = time.perf_counter()

                    latency_ms = (end - start) * 1000.0

                    postgres_metrics.add_success(
                        latency_ms
                    )

                    pg_status = result_value(
                        postgres_result,
                        "status",
                        "?",
                    )

                    pg_score = result_value(
                        postgres_result,
                        "risk_score",
                        "?",
                    )

                    print(
                        f" | PG={pg_status}"
                        f"/{pg_score}"
                        f" ({latency_ms:.3f} ms)",
                        end="",
                    )

                except Exception as exc:
                    postgres_metrics.add_error()

                    print(
                        f" | PG ERROR: {exc}",
                        end="",
                    )

            # ----------------------------------------------------------
            # VoltDB
            # ----------------------------------------------------------

            if args.target in ("voltdb", "both"):
                try:
                    start = time.perf_counter()

                    voltdb_result = process_voltdb(
                        voltdb_client,
                        transaction,
                        args.voltdb_api_url,
                    )

                    end = time.perf_counter()

                    latency_ms = (end - start) * 1000.0

                    voltdb_metrics.add_success(
                        latency_ms
                    )

                    vdb_status = result_value(
                        voltdb_result,
                        "status",
                        "?",
                    )

                    vdb_score = result_value(
                        voltdb_result,
                        "risk_score",
                        "?",
                    )

                    print(
                        f" | VDB={vdb_status}"
                        f"/{vdb_score}"
                        f" ({latency_ms:.3f} ms)",
                        end="",
                    )

                except Exception as exc:
                    voltdb_metrics.add_error()

                    print(
                        f" | VDB ERROR: {exc}",
                        end="",
                    )

            # ----------------------------------------------------------
            # Parity
            # ----------------------------------------------------------

            if (
                args.target == "both"
                and postgres_result is not None
                and voltdb_result is not None
            ):
                parity_error = check_parity(
                    transaction,
                    postgres_result,
                    voltdb_result,
                )

                if parity_error is not None:
                    parity_errors.append(
                        parity_error
                    )

                    print(
                        f" | PARITY ERROR: {parity_error}",
                        end="",
                    )
                else:
                    print(
                        " | PARITY=OK",
                        end="",
                    )

            print()

    except KeyboardInterrupt:
        print(
            "\n[INFO] Elaborazione interrotta dall'utente."
        )

    except Exception as exc:
        print(
            f"\n[ERRORE] {exc}",
            file=sys.stderr,
        )

        return 1

    finally:
        global_end = time.perf_counter()

        if args.target in ("postgres", "both"):
            postgres_metrics.finish()

        if args.target in ("voltdb", "both"):
            voltdb_metrics.finish()

    global_time = global_end - global_start

    # ------------------------------------------------------------------
    # Risultati
    # ------------------------------------------------------------------

    print()
    print("=" * 60)
    print(" RISULTATI STREAM")
    print("=" * 60)

    print(
        f"Transazioni stream : {processed_stream}"
    )

    print(
        f"Tempo stream       : "
        f"{global_time:.3f} s"
    )

    if global_time > 0:
        print(
            f"Stream rate        : "
            f"{processed_stream / global_time:.3f} tx/s"
        )

    # ------------------------------------------------------------------
    # PostgreSQL metrics
    # ------------------------------------------------------------------

    if args.target in ("postgres", "both"):
        print()
        print("-" * 60)
        print(" POSTGRESQL")
        print("-" * 60)

        print(
            f"Transazioni OK     : "
            f"{postgres_metrics.processed}"
        )

        print(
            f"Errori             : "
            f"{postgres_metrics.errors}"
        )

        print(
            f"Tempo totale       : "
            f"{postgres_metrics.total_time:.3f} s"
        )

        print(
            f"Throughput         : "
            f"{postgres_metrics.throughput:.3f} tx/s"
        )

        print(
            f"Latenza media      : "
            f"{postgres_metrics.average_latency:.3f} ms"
        )

        print(
            f"P50                : "
            f"{postgres_metrics.p50:.3f} ms"
        )

        print(
            f"P95                : "
            f"{postgres_metrics.p95:.3f} ms"
        )

        print(
            f"P99                : "
            f"{postgres_metrics.p99:.3f} ms"
        )

        print(
            f"Max latency        : "
            f"{postgres_metrics.max_latency:.3f} ms"
        )

    # ------------------------------------------------------------------
    # VoltDB metrics
    # ------------------------------------------------------------------

    if args.target in ("voltdb", "both"):
        print()
        print("-" * 60)
        print(" VOLTDB")
        print("-" * 60)

        print(
            f"Transazioni OK     : "
            f"{voltdb_metrics.processed}"
        )

        print(
            f"Errori             : "
            f"{voltdb_metrics.errors}"
        )

        print(
            f"Tempo totale       : "
            f"{voltdb_metrics.total_time:.3f} s"
        )

        print(
            f"Throughput         : "
            f"{voltdb_metrics.throughput:.3f} tx/s"
        )

        print(
            f"Latenza media      : "
            f"{voltdb_metrics.average_latency:.3f} ms"
        )

        print(
            f"P50                : "
            f"{voltdb_metrics.p50:.3f} ms"
        )

        print(
            f"P95                : "
            f"{voltdb_metrics.p95:.3f} ms"
        )

        print(
            f"P99                : "
            f"{voltdb_metrics.p99:.3f} ms"
        )

        print(
            f"Max latency        : "
            f"{voltdb_metrics.max_latency:.3f} ms"
        )

    # ------------------------------------------------------------------
    # Parity
    # ------------------------------------------------------------------

    if args.target == "both":
        print()
        print("-" * 60)
        print(" PARITÀ POSTGRESQL / VOLTDB")
        print("-" * 60)

        print(
            f"Mismatch            : "
            f"{len(parity_errors)}"
        )

        if parity_errors:
            print()
            print("Prime differenze:")

            for error in parity_errors[:10]:
                print(f"  - {error}")
        else:
            print(
                "OK: risk_score e status coincidono "
                "per tutte le transazioni elaborate."
            )

    print()
    print("=" * 60)
    print(" STREAM COMPLETATO")
    print("=" * 60)

    # Se ci sono mismatch, il processo termina con errore.
    if parity_errors:
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())