# Sistema Antifrode Finanziaria Real-Time con VoltDB

## Obiettivo del progetto

Il progetto ha come obiettivo la realizzazione di un sistema di **rilevamento delle frodi finanziarie in tempo reale**, basato su **VoltDB** e sviluppato interamente in **Python**.

Il sistema simulerà un flusso continuo di transazioni finanziarie. Ogni transazione verrà analizzata in tempo reale attraverso un insieme di **regole di rischio**, al fine di determinare uno stato finale:

* **APPROVATA**
* **IN REVISIONE**
* **RIFIUTATA**

Il progetto prevede inoltre un confronto sperimentale tra VoltDB e un **database relazionale tradizionale**, come PostgreSQL, valutando sia le prestazioni operative sia l'efficacia nel rilevamento delle transazioni fraudolente.

---

## Architettura generale

L'architettura proposta è la seguente:

```text
                 SIMULATORE TRANSAZIONI
                         │
                         │ Python
                         ▼
                ┌──────────────────┐
                │ Transaction      │
                │ Generator        │
                └────────┬─────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
        ┌───────────┐         ┌────────────┐
        │  VoltDB   │         │ PostgreSQL │
        └─────┬─────┘         └──────┬─────┘
              │                      │
              │                      │
              ▼                      ▼
        Fraud Detection        Fraud Detection
              │                      │
              └──────────┬───────────┘
                         │
                         ▼
                  Benchmark Engine
                         │
                         ▼
                  Metriche e Report
```

L'obiettivo è garantire che entrambi i database elaborino le stesse transazioni e utilizzino la stessa logica di valutazione del rischio, così da rendere il confronto il più possibile equo.

---

## Flusso di elaborazione

Il sistema seguirà il seguente flusso:

```text
1. Generazione della transazione
              │
              ▼
2. Inserimento nel database
              │
              ▼
3. Recupero dello storico del cliente
              │
              ▼
4. Applicazione delle regole antifrode
              │
              ▼
5. Calcolo del Risk Score
              │
              ▼
6. Determinazione dello stato
              │
              ├── APPROVATA
              ├── IN REVISIONE
              └── RIFIUTATA
              │
              ▼
7. Salvataggio del risultato
              │
              ▼
8. Raccolta delle metriche
```

---

# Modello della transazione

Ogni transazione potrebbe contenere le seguenti informazioni:

```text
transaction_id
user_id
timestamp
amount
merchant_id
country
device_id
ip_address
```

A queste informazioni possono essere aggiunti ulteriori attributi utili per il rilevamento delle frodi, ad esempio:

```text
currency
payment_method
merchant_category
latitude
longitude
card_id
```

---

# Motore di valutazione del rischio

Il sistema utilizzerà un insieme di regole per calcolare un **Risk Score**.

Un esempio di regole potrebbe essere:

| Regola                                    | Punteggio |
| ----------------------------------------- | --------: |
| Importo > 1.000 €                         |       +20 |
| Importo > 5.000 €                         |       +40 |
| Nuovo dispositivo                         |       +20 |
| Nuova nazione                             |       +25 |
| Più di 5 transazioni in 1 minuto          |       +30 |
| Transazioni geograficamente incompatibili |       +50 |
| Merchant ad alto rischio                  |       +30 |

Il punteggio complessivo determinerà lo stato della transazione.

```text
Risk Score < 30
    │
    ▼
APPROVATA


30 <= Risk Score < 60
    │
    ▼
IN REVISIONE


Risk Score >= 60
    │
    ▼
RIFIUTATA
```

Le regole potranno essere modificate e parametrizzate per consentire diversi scenari sperimentali.

---

# Simulazione delle transazioni

Il simulatore Python genererà un flusso di transazioni composto da:

* transazioni legittime;
* transazioni fraudolente.

Le transazioni fraudolente potranno simulare diversi comportamenti.

## Tipologie di frode

### Velocity Attack

Generazione di un numero elevato di transazioni in un intervallo temporale molto breve.

### Account Takeover

Cambio improvviso di dispositivo, indirizzo IP o localizzazione geografica.

### Geographical Anomaly

Transazioni effettuate in luoghi geograficamente incompatibili in un intervallo di tempo troppo breve.

### High-Value Transaction

Transazione con un importo significativamente superiore rispetto al comportamento abituale dell'utente.

### Card Testing

Generazione di numerose transazioni di piccolo importo in rapida successione.

### Multiple Merchants

Esecuzione di transazioni presso numerosi merchant differenti in un breve intervallo temporale.

---

# Ground Truth

Per valutare l'efficacia del sistema antifrode, ogni transazione generata dal simulatore avrà un'etichetta interna che rappresenta il suo stato reale.

Ad esempio:

```text
transaction_id | actual_fraud
--------------------------------
T001           | false
T002           | false
T003           | true
T004           | false
T005           | true
```

Il sistema antifrode produrrà invece una decisione:

```text
transaction_id | decision
--------------------------------
T001           | APPROVED
T002           | REVIEW
T003           | DECLINED
T004           | APPROVED
T005           | REVIEW
```

Il confronto tra il valore reale (`actual_fraud`) e la decisione del sistema permetterà di valutare l'efficacia del sistema di rilevamento.

---

# Valutazione del rilevamento delle frodi

Il sistema potrà essere valutato attraverso una **Confusion Matrix**.

```text
                         Predicted
                    Fraud       Normal
                 ┌───────────┬───────────┐
Actual Fraud     │ TP        │ FN        │
                 ├───────────┼───────────┤
Actual Normal    │ FP        │ TN        │
                 └───────────┴───────────┘
```

Le principali metriche saranno:

* **True Positive (TP)**: frode correttamente identificata;
* **True Negative (TN)**: transazione legittima correttamente accettata;
* **False Positive (FP)**: transazione legittima classificata come fraudolenta;
* **False Negative (FN)**: frode non rilevata.

Da questi valori sarà possibile calcolare:

* Precision;
* Recall;
* F1-Score;
* False Positive Rate;
* False Negative Rate.

---

# Confronto VoltDB vs PostgreSQL

Il progetto prevede un confronto tra:

1. **VoltDB**
2. **PostgreSQL**

Entrambi i sistemi dovranno elaborare:

* lo stesso dataset;
* lo stesso flusso di transazioni;
* le stesse regole antifrode;
* lo stesso insieme di scenari fraudolenti.

In questo modo sarà possibile isolare maggiormente l'impatto del database sulle prestazioni del sistema.

| Aspetto                 | VoltDB   | PostgreSQL |
| ----------------------- | -------- | ---------- |
| Inserimento transazioni | ✓        | ✓          |
| Elaborazione real-time  | ✓        | ✓          |
| Valutazione del rischio | ✓        | ✓          |
| Accesso allo storico    | ✓        | ✓          |
| Throughput              | Misurato | Misurato   |
| Latenza                 | Misurata | Misurata   |
| CPU                     | Misurata | Misurata   |
| RAM                     | Misurata | Misurata   |
| Rilevamento frodi       | Misurato | Misurato   |
| Scalabilità             | Testata  | Testata    |

---

# Metriche prestazionali

Per ogni transazione verranno registrati almeno:

```text
timestamp_inizio
timestamp_fine
latency
```

La latenza sarà calcolata come:

```text
latency = timestamp_fine - timestamp_inizio
```

Le principali metriche saranno:

### Throughput

Numero di transazioni elaborate al secondo.

```text
TPS = Transactions Per Second
```

### Latenza media

Tempo medio necessario per elaborare una transazione.

### P50

Il 50% delle transazioni viene elaborato entro questo tempo.

### P95

Il 95% delle transazioni viene elaborato entro questo tempo.

### P99

Il 99% delle transazioni viene elaborato entro questo tempo.

### Maximum Latency

Il tempo massimo di elaborazione registrato.

---

# Piano sperimentale

Il confronto potrà essere organizzato attraverso tre esperimenti principali.

## Esperimento A — Carico crescente

Il sistema verrà testato con dataset di dimensioni differenti:

```text
1.000 transazioni
10.000 transazioni
100.000 transazioni
1.000.000 transazioni
```

Per ogni scenario verranno misurati:

* throughput;
* latenza;
* utilizzo CPU;
* utilizzo RAM;
* accuratezza del rilevamento delle frodi.

---

## Esperimento B — Throughput crescente

Il numero di transazioni al secondo verrà progressivamente incrementato:

```text
100 TPS
1.000 TPS
5.000 TPS
10.000 TPS
50.000 TPS
100.000 TPS
```

L'obiettivo sarà individuare il punto in cui il sistema inizia a degradare in termini di:

* latenza;
* throughput;
* errori;
* transazioni non elaborate.

Questo permetterà di identificare il **breakpoint** del sistema.

---

## Esperimento C — Complessità delle regole

Verranno testati diversi livelli di complessità del motore antifrode:

```text
Scenario 1
3 regole antifrode

Scenario 2
10 regole antifrode

Scenario 3
30 regole antifrode

Scenario 4
50 regole antifrode
```

L'obiettivo sarà analizzare l'impatto della complessità della logica antifrode sulle prestazioni dei due sistemi.

---

# Architettura Docker

Il progetto sarà organizzato tramite Docker Compose.

Una possibile struttura è:

```text
fraud-detection/
│
├── docker-compose.yml
│
├── services/
│   │
│   ├── simulator/
│   │   ├── Dockerfile
│   │   └── app/
│   │       └── generator.py
│   │
│   ├── voltdb-engine/
│   │   ├── Dockerfile
│   │   └── app/
│   │       ├── client.py
│   │       └── risk_engine.py
│   │
│   ├── postgres-engine/
│   │   ├── Dockerfile
│   │   └── app/
│   │       ├── client.py
│   │       └── risk_engine.py
│   │
│   └── benchmark/
│       ├── Dockerfile
│       └── app/
│           ├── benchmark.py
│           └── metrics.py
│
├── database/
│   ├── voltdb/
│   │   └── schema.sql
│   │
│   └── postgres/
│       └── schema.sql
│
├── results/
│
└── README.md
```

L'architettura Docker finale sarà composta indicativamente dai seguenti servizi:

```text
┌─────────────────────┐
│ Transaction         │
│ Simulator           │
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
┌───────────┐ ┌────────────┐
│  VoltDB   │ │ PostgreSQL │
└─────┬─────┘ └──────┬─────┘
      │              │
      │              │
      ▼              ▼
Fraud Detection  Fraud Detection
      │              │
      └──────┬───────┘
             │
             ▼
       ┌────────────┐
       │ Benchmark  │
       │ Engine     │
       └─────┬──────┘
             │
             ▼
       Results / CSV
             │
             ▼
       Grafici e Analisi
```

L'obiettivo finale è consentire l'avvio dell'intero ambiente tramite un singolo comando:

```bash
docker compose up
```

---

# Obiettivo della ricerca

La domanda di ricerca principale potrebbe essere formulata nel seguente modo:

> **"Valutazione delle prestazioni e dell'efficacia di VoltDB rispetto a un database relazionale tradizionale nell'elaborazione real-time di transazioni finanziarie per il rilevamento delle frodi."**

Il progetto mira quindi a valutare se l'utilizzo di VoltDB possa offrire vantaggi significativi rispetto a un database relazionale tradizionale in uno scenario caratterizzato da:

* elevato numero di transazioni;
* necessità di elaborazione in tempo reale;
* bassa latenza;
* elevato throughput;
* accesso frequente ai dati storici;
* applicazione di regole antifrode;
* necessità di identificare rapidamente comportamenti anomali.

Il confronto finale considererà sia gli aspetti **prestazionali** sia quelli relativi alla **qualità del rilevamento delle frodi**, mantenendo invariata la logica antifrode tra le due implementazioni.
