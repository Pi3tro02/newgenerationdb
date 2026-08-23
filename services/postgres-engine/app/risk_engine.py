"""
Modulo per la valutazione del rischio delle transazioni (compatibilità per PostgreSQL Engine).
Re-esporta le funzioni dal modulo condiviso `services.common.risk_engine`.
"""

import os
import sys

# Assicura la raggiungibilità del modulo `services.common` nel sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_services_dir = os.path.abspath(os.path.join(_current_dir, "../.."))
_workspace_root = os.path.abspath(os.path.join(_services_dir, ".."))
for _p in [_workspace_root, _services_dir]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from services.common.risk_engine import evaluate_transaction, build_alert_reason
except ImportError:
    from common.risk_engine import evaluate_transaction, build_alert_reason

__all__ = ["evaluate_transaction", "build_alert_reason"]

