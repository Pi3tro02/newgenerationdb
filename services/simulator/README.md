# Real-time Transaction Simulator

Entry point:

```bash
python services/simulator/simulator.py --target postgres --limit 100 --tps 10
python services/simulator/simulator.py --target voltdb --limit 100 --tps 10
python services/simulator/simulator.py --target both --limit 100 --tps 10

## Verifica rapida

Dopo aver applicato modifiche al risk engine, ai client o al simulatore, è possibile eseguire questi controlli minimi:

```bash
python -m unittest services.common.test_risk_engine
python -m py_compile services/voltdb-engine/app/client.py services/voltdb-engine/app/simulator.py services/simulator/simulator.py
python services/simulator/simulator.py --target voltdb --limit 1
