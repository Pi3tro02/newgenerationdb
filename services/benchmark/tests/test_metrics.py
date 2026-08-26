"""Unit tests per il modulo services/benchmark/app/metrics.py."""

import unittest
from pathlib import Path
import sys

SERVICES_DIR = Path(__file__).resolve().parents[2]
BENCHMARK_APP_DIR = SERVICES_DIR / "benchmark" / "app"
if str(BENCHMARK_APP_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARK_APP_DIR))

from metrics import (
    compute_confusion_matrix,
    compute_classification_metrics,
    evaluate_fraud_detection,
    format_metrics_report,
)


class TestMetricsCalculation(unittest.TestCase):

    def test_compute_confusion_matrix(self):
        y_true = [1, 1, 0, 0, 1, 0]
        y_pred = [1, 0, 1, 0, 1, 0]
        # Cases:
        # (1, 1) -> TP: 2 (index 0, 4)
        # (1, 0) -> FN: 1 (index 1)
        # (0, 1) -> FP: 1 (index 2)
        # (0, 0) -> TN: 2 (index 3, 5)
        cm = compute_confusion_matrix(y_true, y_pred)
        self.assertEqual(cm["tp"], 2)
        self.assertEqual(cm["fn"], 1)
        self.assertEqual(cm["fp"], 1)
        self.assertEqual(cm["tn"], 2)
        self.assertEqual(cm["total"], 6)

    def test_compute_classification_metrics(self):
        tp, tn, fp, fn = 80, 900, 10, 10
        m = compute_classification_metrics(tp, tn, fp, fn)

        self.assertAlmostEqual(m["precision"], 80 / 90) # ~0.8889
        self.assertAlmostEqual(m["recall"], 80 / 90)    # ~0.8889
        self.assertAlmostEqual(m["f1_score"], 80 / 90)  # ~0.8889
        self.assertAlmostEqual(m["false_positive_rate"], 10 / 910)
        self.assertAlmostEqual(m["false_negative_rate"], 10 / 90)
        self.assertAlmostEqual(m["accuracy"], 980 / 1000)
        self.assertAlmostEqual(m["specificity"], 900 / 910)

    def test_edge_cases_zero_divisions(self):
        # All zeros
        m = compute_classification_metrics(0, 0, 0, 0)
        self.assertEqual(m["precision"], 0.0)
        self.assertEqual(m["recall"], 0.0)
        self.assertEqual(m["f1_score"], 0.0)
        self.assertEqual(m["false_positive_rate"], 0.0)
        self.assertEqual(m["false_negative_rate"], 0.0)
        self.assertEqual(m["accuracy"], 0.0)

    def test_evaluate_fraud_detection_strict_and_broad(self):
        records = [
            {"fraud_label": "1", "status": "BLOCKED"},   # TP strict & broad
            {"fraud_label": "1", "status": "REVIEW"},    # FN strict, TP broad
            {"fraud_label": "1", "status": "APPROVED"},  # FN strict & broad
            {"fraud_label": "0", "status": "APPROVED"},  # TN strict & broad
            {"fraud_label": "0", "status": "REVIEW"},    # TN strict, FP broad
            {"fraud_label": "0", "status": "BLOCKED"},   # FP strict & broad
        ]

        res = evaluate_fraud_detection(records)
        self.assertEqual(res["total_evaluated"], 6)

        # Strict: only BLOCKED is predicted fraud (1)
        strict = res["strict_mode"]
        self.assertEqual(strict["tp"], 1)  # row 0
        self.assertEqual(strict["tn"], 2)  # row 3, 4
        self.assertEqual(strict["fp"], 1)  # row 5
        self.assertEqual(strict["fn"], 2)  # row 1, 2

        # Broad: BLOCKED or REVIEW is predicted fraud (1)
        broad = res["broad_mode"]
        self.assertEqual(broad["tp"], 2)  # row 0, 1
        self.assertEqual(broad["tn"], 1)  # row 3
        self.assertEqual(broad["fp"], 2)  # row 4, 5
        self.assertEqual(broad["fn"], 1)  # row 2

    def test_evaluate_fraud_detection_handles_missing_or_invalid(self):
        records = [
            {"fraud_label": "1", "status": "BLOCKED"},
            {"fraud_label": "invalid", "status": "BLOCKED"},
            {"status": "BLOCKED"},
            {"fraud_label": "0", "status": ""},
        ]
        res = evaluate_fraud_detection(records)
        self.assertEqual(res["total_evaluated"], 1)
        self.assertEqual(res["strict_mode"]["tp"], 1)

    def test_format_metrics_report(self):
        records = [
            {"fraud_label": 1, "status": "BLOCKED"},
            {"fraud_label": 0, "status": "APPROVED"},
        ]
        res = evaluate_fraud_detection(records)
        report = format_metrics_report(res, title="TEST REPORT")
        self.assertIn("TEST REPORT", report)
        self.assertIn("MODALITA SEVERA", report)
        self.assertIn("MODALITA AMPIA", report)
        self.assertIn("Precision", report)
        self.assertIn("Recall", report)


if __name__ == "__main__":
    unittest.main()
