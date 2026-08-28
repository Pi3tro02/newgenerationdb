"""Modulo per il calcolo delle metriche di valutazione del rilevamento frodi.

Confronta la ground truth (fraud_label) con la decisione del sistema (status)
in due modalita:
  - Severa (Strict): solo BLOCKED e' considerata frode predetta.
  - Ampia (Broad): REVIEW o BLOCKED sono considerate frode predetta.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Union


def compute_confusion_matrix(
    y_true: Iterable[Union[int, str, bool]],
    y_pred: Iterable[Union[int, str, bool]],
) -> Dict[str, int]:
    """Calcola True Positive, True Negative, False Positive, False Negative.
    
    Args:
        y_true: Iterable di valori binari effettivi (1 / True / '1' = frode, 0 = legittimo)
        y_pred: Iterable di valori binari predetti (1 / True / '1' = frode predetta, 0 = legittimo)
        
    Returns:
        Dizionario con 'tp', 'tn', 'fp', 'fn', 'total'.
    """
    tp = 0
    tn = 0
    fp = 0
    fn = 0

    for actual, pred in zip(y_true, y_pred):
        actual_bool = bool(int(actual)) if isinstance(actual, (int, str)) and str(actual).isdigit() else bool(actual)
        pred_bool = bool(int(pred)) if isinstance(pred, (int, str)) and str(pred).isdigit() else bool(pred)

        if actual_bool and pred_bool:
            tp += 1
        elif not actual_bool and not pred_bool:
            tn += 1
        elif not actual_bool and pred_bool:
            fp += 1
        else:
            fn += 1

    return {
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "total": tp + tn + fp + fn,
    }


def compute_classification_metrics(tp: int, tn: int, fp: int, fn: int) -> Dict[str, float]:
    """Calcola le metriche statistiche a partire dai valori della matrice di confusione.
    
    Metriche calcolate:
      - precision = TP / (TP + FP)
      - recall (sensitivity) = TP / (TP + FN)
      - f1_score = 2 * (precision * recall) / (precision + recall)
      - false_positive_rate (FPR) = FP / (FP + TN)
      - false_negative_rate (FNR) = FN / (TP + FN) = 1 - recall
      - accuracy = (TP + TN) / (TP + TN + FP + FN)
      - specificity (TNR) = TN / (TN + FP)
    """
    total = tp + tn + fp + fn

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    fnr = fn / (tp + fn) if (tp + fn) > 0 else 0.0
    accuracy = (tp + tn) / total if total > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0

    return {
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "total": total,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "false_positive_rate": fpr,
        "false_negative_rate": fnr,
        "accuracy": accuracy,
        "specificity": specificity,
    }


def evaluate_fraud_detection(
    records: Iterable[Dict[str, Any]],
    ground_truth_key: str = "fraud_label",
    status_key: str = "status",
) -> Dict[str, Any]:
    """Valuta le predizioni del sistema sia in modalita Severa (Strict) sia Ampia (Broad).
    
    - Modalita Severa (Strict):
        status == 'BLOCKED' -> predetto 1 (Frode)
        status in {'REVIEW', 'APPROVED'} -> predetto 0 (Normale)
        
    - Modalita Ampia (Broad / Prudenziale):
        status in {'BLOCKED', 'REVIEW'} -> predetto 1 (Frode)
        status == 'APPROVED' -> predetto 0 (Normale)
        
    Returns:
        Dizionario contenente le metriche per entrambe le modalita e il conteggio di classi e stati.
    """
    y_true: List[int] = []
    y_pred_strict: List[int] = []
    y_pred_broad: List[int] = []

    status_counts: Dict[str, int] = {"APPROVED": 0, "REVIEW": 0, "BLOCKED": 0, "OTHER": 0}
    ground_truth_counts: Dict[int, int] = {0: 0, 1: 0}

    total_records = 0

    for r in records:
        raw_gt = r.get(ground_truth_key)
        if raw_gt is None:
            continue

        try:
            gt = int(raw_gt)
        except (ValueError, TypeError):
            continue

        st = str(r.get(status_key, "")).strip().upper()
        if not st:
            continue

        total_records += 1
        ground_truth_counts[gt] = ground_truth_counts.get(gt, 0) + 1

        if st in status_counts:
            status_counts[st] += 1
        else:
            status_counts["OTHER"] += 1

        y_true.append(gt)

        # Modalita Severa: solo BLOCKED e' considerata frode predetta
        y_pred_strict.append(1 if st == "BLOCKED" else 0)

        # Modalita Ampia: REVIEW o BLOCKED sono considerate frode predetta
        y_pred_broad.append(1 if st in ("BLOCKED", "REVIEW") else 0)

    cm_strict = compute_confusion_matrix(y_true, y_pred_strict)
    metrics_strict = compute_classification_metrics(
        cm_strict["tp"], cm_strict["tn"], cm_strict["fp"], cm_strict["fn"]
    )

    cm_broad = compute_confusion_matrix(y_true, y_pred_broad)
    metrics_broad = compute_classification_metrics(
        cm_broad["tp"], cm_broad["tn"], cm_broad["fp"], cm_broad["fn"]
    )

    return {
        "total_evaluated": total_records,
        "ground_truth_distribution": {
            "legitimate_0": ground_truth_counts.get(0, 0),
            "fraud_1": ground_truth_counts.get(1, 0),
            "fraud_prevalence_pct": (
                (ground_truth_counts.get(1, 0) / total_records * 100) if total_records > 0 else 0.0
            ),
        },
        "status_distribution": status_counts,
        "strict_mode": metrics_strict,
        "broad_mode": metrics_broad,
    }


def format_metrics_report(results: Dict[str, Any], title: str = "VALUTAZIONE RILEVAMENTO FRODI") -> str:
    """Genera un report testuale formattato delle metriche."""
    lines = []
    lines.append("=" * 68)
    lines.append(f" {title.center(66)} ")
    lines.append("=" * 68)
    lines.append(f"Totale transazioni valutate : {results['total_evaluated']:,}")

    gt_dist = results.get("ground_truth_distribution", {})
    lines.append(
        f"Distribuzione Ground Truth   : Legittime = {gt_dist.get('legitimate_0', 0):,} "
        f"| Frodi = {gt_dist.get('fraud_1', 0):,} ({gt_dist.get('fraud_prevalence_pct', 0.0):.2f}%)"
    )

    st_dist = results.get("status_distribution", {})
    lines.append(
        f"Distribuzione Decisioni      : APPROVED = {st_dist.get('APPROVED', 0):,} "
        f"| REVIEW = {st_dist.get('REVIEW', 0):,} "
        f"| BLOCKED = {st_dist.get('BLOCKED', 0):,}"
    )
    lines.append("-" * 68)

    for mode_name, key, desc in [
        ("MODALITA SEVERA (STRICT)", "strict_mode", "Solo BLOCKED = Frode predetta"),
        ("MODALITA AMPIA (BROAD)", "broad_mode", "REVIEW o BLOCKED = Frode predetta"),
    ]:
        m = results[key]
        lines.append(f"\n>>> {mode_name} ({desc})")
        lines.append("  Matrice di Confusione:")
        lines.append(f"    - True Positives  (TP) : {m['tp']:>7,}  (Frodi correttamente rilevate)")
        lines.append(f"    - True Negatives  (TN) : {m['tn']:>7,}  (Transazioni legittime approvate)")
        lines.append(f"    - False Positives (FP) : {m['fp']:>7,}  (Falsi allarmi su legittime)")
        lines.append(f"    - False Negatives (FN) : {m['fn']:>7,}  (Frodi sfuggite / mancate)")
        lines.append("  Metriche:")
        lines.append(f"    - Precision            : {m['precision'] * 100:>7.2f}%")
        lines.append(f"    - Recall (Sensitivity) : {m['recall'] * 100:>7.2f}%")
        lines.append(f"    - F1-Score             : {m['f1_score'] * 100:>7.2f}%")
        lines.append(f"    - False Positive Rate  : {m['false_positive_rate'] * 100:>7.2f}%")
        lines.append(f"    - False Negative Rate  : {m['false_negative_rate'] * 100:>7.2f}%")
        lines.append(f"    - Accuracy             : {m['accuracy'] * 100:>7.2f}%")
        lines.append(f"    - Specificity          : {m['specificity'] * 100:>7.2f}%")

    lines.append("=" * 68)
    return "\n".join(lines)


def load_csv_records(csv_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Carica i record da un file CSV."""
    records = []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Calcola le metriche di rilevamento frodi (Confusion Matrix, Precision, Recall, F1, FPR, FNR)."
    )
    parser.add_argument(
        "--csv",
        type=str,
        default="transactions.csv",
        help="Percorso del file CSV contenente almeno 'fraud_label' e 'status' (default: transactions.csv)",
    )
    parser.add_argument(
        "--ground-truth-key",
        type=str,
        default="fraud_label",
        help="Nome della colonna di ground truth (default: fraud_label)",
    )
    parser.add_argument(
        "--status-key",
        type=str,
        default="status",
        help="Nome della colonna dello status predetto (default: status)",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Percorso opzionale per salvare i risultati in formato JSON",
    )

    args = parser.parse_args()

    csv_file = Path(args.csv)
    if not csv_file.exists():
        print(f"[ERRORE] File non trovato: {csv_file}", file=sys.stderr)
        return 1

    records = load_csv_records(csv_file)
    if not records:
        print(f"[ERRORE] Il file {csv_file} e' vuoto.", file=sys.stderr)
        return 1

    results = evaluate_fraud_detection(
        records,
        ground_truth_key=args.ground_truth_key,
        status_key=args.status_key,
    )

    print(format_metrics_report(results, title=f"METRICHE FRODI - {csv_file.name}"))

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n[INFO] Risultati JSON salvati in: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
