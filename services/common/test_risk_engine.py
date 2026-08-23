"""
Unit test per il risk engine condiviso e la retrocompatibilità degli engine PostgreSQL e VoltDB.
Eseguibile sia con pytest che con python -m unittest.
"""

from datetime import datetime
import os
import sys
import unittest

# Setup path per i moduli services
_current_dir = os.path.dirname(os.path.abspath(__file__))
_services_dir = os.path.abspath(os.path.join(_current_dir, "../.."))
_workspace_root = os.path.abspath(os.path.join(_services_dir, ".."))

for p in [_workspace_root, _services_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from services.common.risk_engine import evaluate_transaction, build_alert_reason


class TestRiskEngine(unittest.TestCase):
    def setUp(self):
        self.base_tx = {
            "amount": 100.0,
            "country": "IT",
            "transaction_time": datetime(2026, 5, 1, 14, 0, 0),
            "channel": "pos",
            "device_id": "DEV_123"
        }
        self.base_cust = {
            "home_country": "IT",
            "risk_profile": "low",
            "avg_transaction_amount": 100.0
        }
        self.base_card = {
            "card_status": "active"
        }
        self.base_merch = {
            "risk_level": "low"
        }

    def test_no_rules_triggered(self):
        res = evaluate_transaction(self.base_tx, self.base_cust, self.base_card, self.base_merch)
        self.assertFalse(res["is_foreign_country"])
        self.assertFalse(res["is_night_transaction"])
        self.assertEqual(res["risk_score"], 0)
        self.assertEqual(res["status"], "APPROVED")

    def test_high_amount_rule(self):
        tx = dict(self.base_tx, amount=600.0)
        res = evaluate_transaction(tx, self.base_cust, self.base_card, self.base_merch)
        self.assertEqual(res["risk_score"], 30)
        self.assertEqual(res["status"], "APPROVED")

    def test_night_transaction_rule(self):
        tx = dict(self.base_tx, transaction_time=datetime(2026, 5, 1, 3, 0, 0))
        res = evaluate_transaction(tx, self.base_cust, self.base_card, self.base_merch)
        self.assertTrue(res["is_night_transaction"])
        self.assertEqual(res["risk_score"], 10)

    def test_night_transaction_from_string(self):
        tx = dict(self.base_tx, transaction_time="2026-05-01 02:30:00")
        res = evaluate_transaction(tx, self.base_cust, self.base_card, self.base_merch)
        self.assertTrue(res["is_night_transaction"])
        self.assertEqual(res["risk_score"], 10)

    def test_foreign_country_rule(self):
        tx = dict(self.base_tx, country="FR")
        res = evaluate_transaction(tx, self.base_cust, self.base_card, self.base_merch)
        self.assertTrue(res["is_foreign_country"])
        self.assertEqual(res["risk_score"], 20)

    def test_merchant_risk_levels(self):
        m_high = dict(self.base_merch, risk_level="high")
        res_high = evaluate_transaction(self.base_tx, self.base_cust, self.base_card, m_high)
        self.assertEqual(res_high["risk_score"], 25)

        m_med = dict(self.base_merch, risk_level="medium")
        res_med = evaluate_transaction(self.base_tx, self.base_cust, self.base_card, m_med)
        self.assertEqual(res_med["risk_score"], 10)

    def test_card_flagged(self):
        card = dict(self.base_card, card_status="flagged")
        res = evaluate_transaction(self.base_tx, self.base_cust, card, self.base_merch)
        self.assertEqual(res["risk_score"], 40)
        self.assertEqual(res["status"], "REVIEW")

    def test_online_new_device(self):
        tx = dict(self.base_tx, channel="online", device_id="DEV_NEW_99")
        res = evaluate_transaction(tx, self.base_cust, self.base_card, self.base_merch)
        self.assertEqual(res["risk_score"], 15)

    def test_customer_high_risk(self):
        cust = dict(self.base_cust, risk_profile="high")
        res = evaluate_transaction(self.base_tx, cust, self.base_card, self.base_merch)
        self.assertEqual(res["risk_score"], 10)

    def test_score_cap_and_blocked_status(self):
        tx = {
            "amount": 600.0,
            "country": "US",
            "transaction_time": datetime(2026, 5, 1, 2, 0, 0),
            "channel": "online",
            "device_id": "DEV_NEW_999"
        }
        cust = dict(self.base_cust, risk_profile="high")
        card = dict(self.base_card, card_status="flagged")
        merch = dict(self.base_merch, risk_level="high")

        res = evaluate_transaction(tx, cust, card, merch)
        self.assertEqual(res["risk_score"], 100)
        self.assertEqual(res["status"], "BLOCKED")

    def test_threshold_boundaries(self):
        # 35 -> APPROVED
        cust_high = dict(self.base_cust, risk_profile="high")
        merch_high = dict(self.base_merch, risk_level="high")
        res35 = evaluate_transaction(self.base_tx, cust_high, self.base_card, merch_high)
        self.assertEqual(res35["risk_score"], 35)
        self.assertEqual(res35["status"], "APPROVED")

        # 40 -> REVIEW
        tx_high_night = dict(self.base_tx, amount=600.0, transaction_time=datetime(2026, 5, 1, 3, 0, 0))
        res40 = evaluate_transaction(tx_high_night, self.base_cust, self.base_card, self.base_merch)
        self.assertEqual(res40["risk_score"], 40)
        self.assertEqual(res40["status"], "REVIEW")

        # 70 -> BLOCKED
        card_flagged = dict(self.base_card, card_status="flagged")
        tx_high = dict(self.base_tx, amount=600.0)
        res70 = evaluate_transaction(tx_high, self.base_cust, card_flagged, self.base_merch)
        self.assertEqual(res70["risk_score"], 70)
        self.assertEqual(res70["status"], "BLOCKED")

    def test_build_alert_reason(self):
        self.assertEqual(build_alert_reason(True, True, True), "high_amount;night_transaction;foreign_country")
        self.assertEqual(build_alert_reason(True, False, False), "high_amount")
        self.assertEqual(build_alert_reason(False, True, False), "night_transaction")
        self.assertEqual(build_alert_reason(False, False, True), "foreign_country")
        self.assertEqual(build_alert_reason(False, False, False), "risk_score_threshold")


if __name__ == "__main__":
    unittest.main()
