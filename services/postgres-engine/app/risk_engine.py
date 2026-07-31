"""
Modulo per la valutazione del rischio delle transazioni (Risk Engine per PostgreSQL).
Puro Python: nessuna dipendenza esterna o I/O database.
"""

from datetime import datetime


def evaluate_transaction(
    transaction: dict,
    customer: dict,
    card: dict,
    merchant: dict
) -> dict:
    """
    Valuta il livello di rischio di una transazione.

    Parametri:
    - transaction: {"amount": float, "country": str, "transaction_time": datetime,
                     "channel": str, "device_id": str}
    - customer: {"home_country": str, "risk_profile": str, "avg_transaction_amount": float}
    - card: {"card_status": str}
    - merchant: {"risk_level": str}

    Ritorna: {
        "is_foreign_country": bool,
        "is_night_transaction": bool,
        "risk_score": int,
        "status": str  # APPROVED | REVIEW | BLOCKED
    }
    """
    # 1. Verifica transazione in paese estero
    is_foreign_country: bool = transaction["country"] != customer["home_country"]

    # 2. Verifica transazione notturna (ora < 6)
    transaction_time: datetime = transaction["transaction_time"]
    is_night_transaction: bool = transaction_time.hour < 6

    # 3. Punteggio di rischio iniziale
    risk_score: int = 0

    # 4. Importo elevato (> 5 volte la media del cliente)
    if float(transaction["amount"]) > float(customer["avg_transaction_amount"]) * 5:
        risk_score += 30

    # 5. Transazione notturna
    if is_night_transaction:
        risk_score += 10

    # 6. Transazione in paese estero
    if is_foreign_country:
        risk_score += 20

    # 7. Livello di rischio dell'esercente
    merchant_risk = merchant.get("risk_level")
    if merchant_risk == "high":
        risk_score += 25
    elif merchant_risk == "medium":
        risk_score += 10

    # 8. Stato della carta
    if card.get("card_status") == "flagged":
        risk_score += 40

    # 9. Canale online con dispositivo nuovo
    channel = transaction.get("channel")
    device_id = transaction.get("device_id") or ""
    if channel == "online" and device_id.startswith("DEV_NEW"):
        risk_score += 15

    # 10. Profilo di rischio del cliente
    if customer.get("risk_profile") == "high":
        risk_score += 10

    # 11. Cap a 100
    risk_score = min(risk_score, 100)

    # 12. Determinazione stato transazione
    if risk_score >= 70:
        status = "BLOCKED"
    elif risk_score >= 40:
        status = "REVIEW"
    else:
        status = "APPROVED"

    return {
        "is_foreign_country": is_foreign_country,
        "is_night_transaction": is_night_transaction,
        "risk_score": risk_score,
        "status": status
    }


def build_alert_reason(is_high_amount: bool, is_night: bool, is_foreign: bool) -> str:
    """
    Costruisce la stringa delle motivazioni dell'alert generato.

    Parametri:
    - is_high_amount: True se l'importo è oltre 5 volte la media del cliente
    - is_night: True se la transazione è notturna
    - is_foreign: True se la transazione è in paese estero

    Ritorna:
    Stringa con i motivi separati da ';' oppure 'risk_score_threshold' se nessuno dei tre è True.
    """
    reasons = []
    if is_high_amount:
        reasons.append("high_amount")
    if is_night:
        reasons.append("night_transaction")
    if is_foreign:
        reasons.append("foreign_country")

    return ";".join(reasons) if reasons else "risk_score_threshold"
