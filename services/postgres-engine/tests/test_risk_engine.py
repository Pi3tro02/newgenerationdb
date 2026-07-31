"""
Suite di unit test per il modulo risk_engine.py tramite pytest.
"""

import os
import sys
from datetime import datetime
import pytest

# Aggiunge il percorso del modulo 'app' al sys.path per consentire l'import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../app")))

from risk_engine import evaluate_transaction, build_alert_reason


@pytest.fixture
def base_context():
    """
    Fornisce un contesto di default neutro in cui nessuna regola di rischio viene attivata.
    """
    transaction = {
        "amount": 100.0,
        "country": "IT",
        "transaction_time": datetime(2026, 5, 1, 14, 0, 0),  # Ora 14: non notturna
        "channel": "pos",
        "device_id": "DEV_123"
    }
    customer = {
        "home_country": "IT",
        "risk_profile": "low",
        "avg_transaction_amount": 100.0
    }
    card = {
        "card_status": "active"
    }
    merchant = {
        "risk_level": "low"
    }
    return transaction, customer, card, merchant


# 1. Nessuna regola attivata -> risk_score=0, status="APPROVED"
def test_no_rules_triggered(base_context):
    transaction, customer, card, merchant = base_context
    result = evaluate_transaction(transaction, customer, card, merchant)

    assert result["is_foreign_country"] is False
    assert result["is_night_transaction"] is False
    assert result["risk_score"] == 0
    assert result["status"] == "APPROVED"


# Parametrizzazione per regole singole (Casi 2-12)
@pytest.mark.parametrize(
    "modifications, expected_score, expected_status",
    [
        # Caso 2: Solo high_amount (amount > avg*5) -> +30, ancora APPROVED
        ({"tx": {"amount": 600.0}}, 30, "APPROVED"),
        # Caso 3: Solo transazione notturna (ora < 6) -> +10
        ({"tx": {"transaction_time": datetime(2026, 5, 1, 3, 0, 0)}}, 10, "APPROVED"),
        # Caso 4: Solo paese estero -> +20
        ({"tx": {"country": "FR"}}, 20, "APPROVED"),
        # Caso 5: Merchant risk_level "high" -> +25
        ({"merch": {"risk_level": "high"}}, 25, "APPROVED"),
        # Caso 6: Merchant risk_level "medium" -> +10
        ({"merch": {"risk_level": "medium"}}, 10, "APPROVED"),
        # Caso 7: Merchant risk_level "low" -> +0
        ({"merch": {"risk_level": "low"}}, 0, "APPROVED"),
        # Caso 8: Carta con card_status "flagged" -> +40 (status -> REVIEW)
        ({"card": {"card_status": "flagged"}}, 40, "REVIEW"),
        # Caso 9: Canale "online" con device_id DEV_NEW -> +15
        ({"tx": {"channel": "online", "device_id": "DEV_NEW_123"}}, 15, "APPROVED"),
        # Caso 10: Canale "online" con device_id NON DEV_NEW -> +0
        ({"tx": {"channel": "online", "device_id": "DEV_EXISTING"}}, 0, "APPROVED"),
        # Caso 11: Canale "pos" con device_id DEV_NEW -> +0
        ({"tx": {"channel": "pos", "device_id": "DEV_NEW_123"}}, 0, "APPROVED"),
        # Caso 12: Cliente risk_profile "high" -> +10
        ({"cust": {"risk_profile": "high"}}, 10, "APPROVED"),
    ],
    ids=[
        "case_2_high_amount",
        "case_3_night_tx",
        "case_4_foreign_country",
        "case_5_merchant_high",
        "case_6_merchant_medium",
        "case_7_merchant_low",
        "case_8_card_flagged",
        "case_9_online_new_device",
        "case_10_online_existing_device",
        "case_11_pos_new_device",
        "case_12_customer_high_risk",
    ]
)
def test_individual_rules(base_context, modifications, expected_score, expected_status):
    transaction, customer, card, merchant = base_context

    if "tx" in modifications:
        transaction.update(modifications["tx"])
    if "cust" in modifications:
        customer.update(modifications["cust"])
    if "card" in modifications:
        card.update(modifications["card"])
    if "merch" in modifications:
        merchant.update(modifications["merch"])

    result = evaluate_transaction(transaction, customer, card, merchant)
    assert result["risk_score"] == expected_score
    assert result["status"] == expected_status


# Test espliciti singoli per massima chiarezza sui casi 2-12
def test_high_amount_rule(base_context):
    transaction, customer, card, merchant = base_context
    transaction["amount"] = 501.0
    result = evaluate_transaction(transaction, customer, card, merchant)
    assert result["risk_score"] == 30
    assert result["status"] == "APPROVED"


def test_night_transaction_rule(base_context):
    transaction, customer, card, merchant = base_context
    transaction["transaction_time"] = datetime(2026, 5, 1, 4, 30, 0)
    result = evaluate_transaction(transaction, customer, card, merchant)
    assert result["is_night_transaction"] is True
    assert result["risk_score"] == 10


def test_foreign_country_rule(base_context):
    transaction, customer, card, merchant = base_context
    transaction["country"] = "DE"
    result = evaluate_transaction(transaction, customer, card, merchant)
    assert result["is_foreign_country"] is True
    assert result["risk_score"] == 20


def test_merchant_high_risk_rule(base_context):
    transaction, customer, card, merchant = base_context
    merchant["risk_level"] = "high"
    result = evaluate_transaction(transaction, customer, card, merchant)
    assert result["risk_score"] == 25


def test_merchant_medium_risk_rule(base_context):
    transaction, customer, card, merchant = base_context
    merchant["risk_level"] = "medium"
    result = evaluate_transaction(transaction, customer, card, merchant)
    assert result["risk_score"] == 10


def test_merchant_low_risk_rule(base_context):
    transaction, customer, card, merchant = base_context
    merchant["risk_level"] = "low"
    result = evaluate_transaction(transaction, customer, card, merchant)
    assert result["risk_score"] == 0


def test_flagged_card_rule(base_context):
    transaction, customer, card, merchant = base_context
    card["card_status"] = "flagged"
    result = evaluate_transaction(transaction, customer, card, merchant)
    assert result["risk_score"] == 40
    assert result["status"] == "REVIEW"


def test_online_new_device_rule(base_context):
    transaction, customer, card, merchant = base_context
    transaction["channel"] = "online"
    transaction["device_id"] = "DEV_NEW_888"
    result = evaluate_transaction(transaction, customer, card, merchant)
    assert result["risk_score"] == 15


def test_online_existing_device_rule(base_context):
    transaction, customer, card, merchant = base_context
    transaction["channel"] = "online"
    transaction["device_id"] = "DEV_KNOWN_888"
    result = evaluate_transaction(transaction, customer, card, merchant)
    assert result["risk_score"] == 0


def test_pos_new_device_rule(base_context):
    transaction, customer, card, merchant = base_context
    transaction["channel"] = "pos"
    transaction["device_id"] = "DEV_NEW_888"
    result = evaluate_transaction(transaction, customer, card, merchant)
    assert result["risk_score"] == 0


def test_customer_high_risk_profile_rule(base_context):
    transaction, customer, card, merchant = base_context
    customer["risk_profile"] = "high"
    result = evaluate_transaction(transaction, customer, card, merchant)
    assert result["risk_score"] == 10


# 13. Combinazione di TUTTE le regole insieme -> risk_score troncato a 100, status="BLOCKED"
def test_all_rules_triggered_score_cap():
    transaction = {
        "amount": 600.0,
        "country": "US",
        "transaction_time": datetime(2026, 5, 1, 2, 0, 0),
        "channel": "online",
        "device_id": "DEV_NEW_999"
    }
    customer = {
        "home_country": "IT",
        "risk_profile": "high",
        "avg_transaction_amount": 100.0
    }
    card = {
        "card_status": "flagged"
    }
    merchant = {
        "risk_level": "high"
    }

    result = evaluate_transaction(transaction, customer, card, merchant)
    # Somma parziale teorica: 30 + 10 + 20 + 25 + 40 + 15 + 10 = 150
    assert result["risk_score"] == 100
    assert result["status"] == "BLOCKED"


# 14. Test dei confini esatti delle soglie (35/39 -> APPROVED, 40 -> REVIEW, 65/69 -> REVIEW, 70 -> BLOCKED)
@pytest.mark.parametrize(
    "modifications, expected_score, expected_status",
    [
        # Score 35 (< 40) -> APPROVED (merchant high: +25, customer high: +10)
        ({"merch": {"risk_level": "high"}, "cust": {"risk_profile": "high"}}, 35, "APPROVED"),
        # Score 40 (>= 40, < 70) -> REVIEW (high_amount: +30, night: +10)
        ({"tx": {"amount": 600.0, "transaction_time": datetime(2026, 5, 1, 3, 0, 0)}}, 40, "REVIEW"),
        # Score 65 (< 70) -> REVIEW (flagged card: +40, merchant high: +25)
        ({"card": {"card_status": "flagged"}, "merch": {"risk_level": "high"}}, 65, "REVIEW"),
        # Score 70 (>= 70) -> BLOCKED (flagged card: +40, high_amount: +30)
        ({"card": {"card_status": "flagged"}, "tx": {"amount": 600.0}}, 70, "BLOCKED"),
    ],
    ids=["boundary_35_approved", "boundary_40_review", "boundary_65_review", "boundary_70_blocked"]
)
def test_threshold_boundaries(base_context, modifications, expected_score, expected_status):
    transaction, customer, card, merchant = base_context

    if "tx" in modifications:
        transaction.update(modifications["tx"])
    if "cust" in modifications:
        customer.update(modifications["cust"])
    if "card" in modifications:
        card.update(modifications["card"])
    if "merch" in modifications:
        merchant.update(modifications["merch"])

    result = evaluate_transaction(transaction, customer, card, merchant)
    assert result["risk_score"] == expected_score
    assert result["status"] == expected_status


# 15. build_alert_reason(True, True, True) -> "high_amount;night_transaction;foreign_country"
def test_build_alert_reason_all_true():
    assert build_alert_reason(True, True, True) == "high_amount;night_transaction;foreign_country"


# 16. build_alert_reason(False, False, False) -> "risk_score_threshold"
def test_build_alert_reason_all_false():
    assert build_alert_reason(False, False, False) == "risk_score_threshold"


# 17. build_alert_reason(True, False, False) -> "high_amount"
def test_build_alert_reason_single():
    assert build_alert_reason(True, False, False) == "high_amount"
