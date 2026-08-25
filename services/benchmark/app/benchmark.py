import argparse
import csv
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
SERVICES_DIR = CURRENT_DIR.parents[1]
WORKSPACE_ROOT = SERVICES_DIR.parent
VOLTDB_APP_DIR = SERVICES_DIR / "voltdb-engine" / "app"

for path in (WORKSPACE_ROOT, SERVICES_DIR, VOLTDB_APP_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from stream import transaction_stream

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def percentile(values, pct):
    if not values:
        return 0.0

    values = sorted(values)
    if len(values) == 1:
        return values[0]

    pos = (len(values) - 1) * pct / 100
    lower = int(pos)
    upper = min(lower + 1, len(values) - 1)
    frac = pos - lower

    return values[lower] + (values[upper] - values[lower]) * frac

def load_client(engine_dir):
    path = SERVICES_DIR / engine_dir / "app" / "client.py"
    spec = importlib.util.spec_from_file_location(engine_dir, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def run_one(target, client, connection_or_url, tx):
    start_time = now_iso()
    t0 = time.perf_counter()

    status = ""
    error = ""

    try:
        result = client.process_transaction(connection_or_url, tx)
        status = result.get("status", "")

    except Exception as exc:
        error = str(exc)

        if target == "postgres" and hasattr(connection_or_url, "rollback"):
            connection_or_url.rollback()

    t1 = time.perf_counter()
    end_time = now_iso()

    return {
        "target": target,
        "transaction_id": tx.get("transaction_id"),
        "start_time": start_time,
        "end_time": end_time,
        "latency_ms": (t1 - t0) * 1000,
        "status": status,
        "error": error,
    }

def find_mismatches(records):
    records_by_transaction = {}

    for record in records:
        transaction_id = record["transaction_id"]

        if transaction_id not in records_by_transaction:
            records_by_transaction[transaction_id] = {}

        records_by_transaction[transaction_id][record["target"]] = record

    mismatches = []

    for transaction_id, target_records in records_by_transaction.items():
        postgres_record = target_records.get("postgres")
        voltdb_record = target_records.get("voltdb")

        if postgres_record is None or voltdb_record is None:
            mismatches.append({
                "transaction_id": transaction_id,
                "type": "missing_target",
                "postgres_status": postgres_record["status"] if postgres_record else None,
                "voltdb_status": voltdb_record["status"] if voltdb_record else None,
                "postgres_error": postgres_record["error"] if postgres_record else None,
                "voltdb_error": voltdb_record["error"] if voltdb_record else None,
            })
            continue

        if postgres_record["status"] != voltdb_record["status"]:
            mismatches.append({
                "transaction_id": transaction_id,
                "type": "status_mismatch",
                "postgres_status": postgres_record["status"],
                "voltdb_status": voltdb_record["status"],
                "postgres_error": postgres_record["error"],
                "voltdb_error": voltdb_record["error"],
            })

    return mismatches

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark PostgreSQL e VoltDB per fraud detection"
    )

    parser.add_argument("--transactions-csv", default="transactions.csv")
    parser.add_argument("--target", choices=["postgres", "voltdb", "both"], default="both")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--tps", type=float, default=None)
    parser.add_argument(
        "--postgres-url",
        default="postgresql://fraud:fraud@localhost:5432/frauddb",
        )
    parser.add_argument(
        "--voltdb-api-url",
        default="http://localhost:8080/api/2.0",
    )
    parser.add_argument("--results-dir", default="results")

    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit deve essere >= 0")

    if args.tps is not None and args.tps <= 0:
        parser.error("--tps deve essere > 0")

    targets = ["postgres", "voltdb"] if args.target == "both" else [args.target]

    clients = {}
    connections = {}


    try:
        if "postgres" in targets:
            clients["postgres"] = load_client("postgres-engine")
            connections["postgres"] = clients["postgres"].connect_db(args.postgres_url)

        if "voltdb" in targets:
            clients["voltdb"] = load_client("voltdb-engine")
            connections["voltdb"] = args.voltdb_api_url

    except Exception as exc:
        print(f"[ERRORE] Setup benchmark fallito: {exc}", file=sys.stderr)
        return 1

    records = []

    benchmark_start = time.perf_counter()

    try:
        for index, tx in enumerate(
            transaction_stream(
                csv_path=args.transactions_csv,
                limit=args.limit,
                tps=args.tps,
            ),
            start=1,
        ):
            transaction_id = tx.get("transaction_id", "?")
            print(f"[{index}] transaction_id={transaction_id}", end="", flush=True)

            for target in targets:
                record = run_one(
                    target=target,
                    client=clients[target],
                    connection_or_url=connections[target],
                    tx=tx,
                )

                records.append(record)

                if record["error"]:
                    print(f" | {target}=ERROR", end="")
                else:
                    print(
                        f" | {target}={record['status']}"
                        f" ({record['latency_ms']:.3f} ms)",
                        end="",
                    )

            print()
    
    except KeyboardInterrupt:
        print("\n[INFO] Benchmark interrotto dall'utente.")
        return_code = 130

    except Exception as exc:
        print(f"\n[ERRORE] Benchmark fallito: {exc}", file=sys.stderr)
        return_code = 1

    else:
        return_code = 0

    benchmark_end = time.perf_counter()
    total_benchmark_time = benchmark_end - benchmark_start

    postgres_conn = connections.get("postgres")
    if postgres_conn is not None:
        try:
            postgres_conn.close()
        except Exception:
            pass

    mismatches = find_mismatches(records) if args.target == "both" else []

    summary = {
        "target": args.target,
        "transactions_csv": args.transactions_csv,
        "limit": args.limit,
        "tps": args.tps,
        "total_benchmark_time_s": total_benchmark_time,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "targets": {}
    }

    for target in targets:
        target_records = [
            record for record in records
            if record["target"] == target
        ]

        latencies = [
            record["latency_ms"] for record in target_records
        ]

        errors = [
            record for record in target_records
            if record["error"]
        ]

        successful = [
            record for record in target_records
            if not record["error"]
        ]

        total_latency_s = sum(latencies) / 1000.0

        summary["targets"][target] = {
            "transactions": len(target_records),
            "successful": len(successful),
            "errors": len(errors),
            "throughput_tx_s": (
                len(target_records) / total_latency_s
                if total_latency_s > 0
                else 0.0
            ),
            "average_latency_ms": (
                sum(latencies) / len(latencies)
                if latencies
                else 0.0
            ),
            "p50_latency_ms": percentile(latencies, 50),
            "p95_latency_ms": percentile(latencies, 95),
            "p99_latency_ms": percentile(latencies, 99),
            "max_latency_ms": max(latencies) if latencies else 0.0,
        }

    results_dir = Path(args.results_dir)
    if not results_dir.is_absolute():
        results_dir = WORKSPACE_ROOT / results_dir

    results_dir.mkdir(parents=True, exist_ok=True)

    run_name = datetime.now().strftime("benchmark_%Y%m%d_%H%M%S")

    csv_path = results_dir / f"{run_name}_transactions.csv"
    json_path = results_dir / f"{run_name}_summary.json"

    fieldnames = [
        "target",
        "transaction_id",
        "start_time",
        "end_time",
        "latency_ms",
        "status",
        "error",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    
    with json_path.open("w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2, ensure_ascii=False)
        file.write("\n")

    print()
    print("=" * 60)
    print(" Risultati Benchmark")
    print("=" * 60)

    for target, metrics in summary["targets"].items():
        print()
        print(target.upper())
        print(f"Transazioni     : {metrics['transactions']}")
        print(f"Successi        : {metrics['successful']}")
        print(f"Errori          : {metrics['errors']}")
        print(f"Throughput      : {metrics['throughput_tx_s']:.3f} tx/s")
        print(f"Latenza media   : {metrics['average_latency_ms']:.3f} ms")
        print(f"P50             : {metrics['p50_latency_ms']:.3f} ms")
        print(f"P95             : {metrics['p95_latency_ms']:.3f} ms")
        print(f"P99             : {metrics['p99_latency_ms']:.3f} ms")
        print(f"Max latency     : {metrics['max_latency_ms']:.3f} ms")

    if args.target == "both":
        print()
        print("PARITÀ POSTGRESQL / VOLTDB")
        print(f"Mismatch        : {len(mismatches)}")

        if mismatches:
            print("Prime differenze:")

            for mismatch in mismatches[:10]:
                print(
                    f"- transaction_id={mismatch['transaction_id']} "
                    f"PG={mismatch['postgres_status']} "
                    f"VoltDB={mismatch['voltdb_status']}"
                )

    print()
    print(f"CSV dettagli    : {csv_path}")
    print(f"JSON summary    : {json_path}")

    return return_code

if __name__ == "__main__":
    raise SystemExit(main())
