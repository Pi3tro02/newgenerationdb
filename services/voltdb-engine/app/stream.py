"""
Transaction stream.

Responsabilità:
- leggere transactions.csv in ordine;
- applicare --limit;
- controllare il ritmo tramite --tps;
- produrre una transazione alla volta.

Il modulo non conosce PostgreSQL o VoltDB.
"""

import csv
import time
from pathlib import Path
from typing import Dict, Iterator, Optional


def transaction_stream(
    csv_path: str,
    limit: int = 0,
    tps: Optional[float] = None,
) -> Iterator[Dict[str, str]]:
    """
    Legge transactions.csv e restituisce le transazioni una alla volta.

    Args:
        csv_path:
            Percorso del file transactions.csv.

        limit:
            Numero massimo di transazioni da emettere.
            0 significa nessun limite.

        tps:
            Target Transactions Per Second.
            None significa nessun controllo di velocità.

    Yields:
        Una transazione alla volta come dizionario.

    Raises:
        FileNotFoundError:
            Se il CSV non esiste.

        ValueError:
            Se limit o tps hanno valori non validi.
    """

    if limit < 0:
        raise ValueError("limit deve essere >= 0")

    if tps is not None and tps <= 0:
        raise ValueError("tps deve essere > 0")

    path = Path(csv_path)

    if not path.exists():
        raise FileNotFoundError(
            f"File transactions.csv non trovato: {csv_path}"
        )

    emitted = 0

    # Tempo di riferimento per il rate limiter.
    #
    # Usiamo un calendario assoluto invece di fare semplicemente
    # sleep(1 / tps) dopo ogni transazione.
    next_send_time = time.perf_counter()

    with path.open(
        mode="r",
        encoding="utf-8",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError("Il CSV non contiene una header.")

        required_columns = {
            "transaction_id",
            "customer_id",
            "card_id",
            "merchant_id",
            "amount",
            "currency",
            "country",
            "transaction_time",
            "channel",
            "device_id",
            "fraud_label",
        }

        missing_columns = required_columns - set(reader.fieldnames)

        if missing_columns:
            raise ValueError(
                "Colonne mancanti nel CSV: "
                + ", ".join(sorted(missing_columns))
            )

        interval = 1.0 / tps if tps is not None else None

        for row in reader:
            if limit > 0 and emitted >= limit:
                break

            # Se è impostato un TPS, aspettiamo fino al momento
            # programmato per l'invio della transazione.
            if interval is not None:
                now = time.perf_counter()

                sleep_time = next_send_time - now

                if sleep_time > 0:
                    time.sleep(sleep_time)

                # Aggiorniamo il prossimo istante previsto.
                next_send_time += interval

                # Se siamo molto in ritardo, evitiamo di accumulare
                # un enorme backlog di sleep.
                now_after_sleep = time.perf_counter()

                if next_send_time < now_after_sleep:
                    next_send_time = now_after_sleep

            emitted += 1

            yield row


def count_transactions(csv_path: str) -> int:
    """
    Conta le transazioni presenti nel CSV.

    Utile per informazioni diagnostiche.
    Non viene utilizzata dal normale streaming.
    """

    path = Path(csv_path)

    if not path.exists():
        raise FileNotFoundError(
            f"File transactions.csv non trovato: {csv_path}"
        )

    with path.open(
        mode="r",
        encoding="utf-8",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        return sum(1 for _ in reader)
        