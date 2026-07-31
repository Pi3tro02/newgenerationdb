# Sistema Antifrode Finanziaria Real-Time con VoltDB

## Obiettivo del progetto

Il progetto ha come obiettivo la realizzazione di un sistema di **rilevamento delle frodi finanziarie in tempo reale**, basato su **VoltDB** e sviluppato interamente in **Python**.

Il sistema simulerà un flusso continuo di transazioni finanziarie, replicando la logica del generatore `dataset.py`. Ogni transazione verrà analizzata in tempo reale attraverso un insieme di **regole di rischio**, al fine di determinare uno stato finale:

* **APPROVED**
* **REVIEW**
* **BLOCKED**

Il progetto prevede inoltre un confronto sperimentale tra VoltDB e il **database relazionale tradizionale**, PostgreSQL, valutando sia le prestazioni operative sia l'efficacia nel rilevamento delle transazioni fraudolente.

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
3. Recupero dello storico del cliente (avg_transaction_amount, risk_profile, home_country)
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
              ├── APPROVED
              ├── REVIEW
              └── BLOCKED
              │
              ▼
7. Salvataggio del risultato
              │
              ▼
8. Raccolta delle metriche
```

---

# Struttura dei dati (schema reale)

Il dataset è composto da 5 file CSV, generati da `dataset.py`, collegati tra loro dalle chiavi indicate.

## customers.csv (5.000 righe)

```text
customer_id            Integer   (PK)
name                    String    "Customer_<id>"
home_country            String    uno tra: Italy, France, Germany, Spain, Netherlands,
                                   Belgium, Austria, Poland, Romania, United Kingdom
risk_profile            String    low | medium | high  (pesi: 75% / 20% / 5%)
avg_transaction_amount  Float     dipende dal risk_profile:
                                     low    -> uniforme(20, 120)
                                     medium -> uniforme(80, 300)
                                     high   -> uniforme(200, 800)
created_at              Date      data casuale nel 2025
```

## cards.csv (6.000 righe)

```text
card_id       Integer   (PK) valori da 90001 in su
customer_id   Integer   (FK -> customers.customer_id)
card_type     String    debit | credit
card_status   String    active | flagged | blocked  (pesi: 94% / 5% / 1%)
daily_limit   Integer   uno tra: 500, 1000, 1500, 3000, 5000
```

Nota: una carta è assegnata a un customer scelto casualmente; un cliente può avere più carte o nessuna.

## merchants.csv (500 righe)

```text
merchant_id     Integer   (PK)
merchant_name   String    "Merchant_<id>"
category        String    grocery | fuel | travel | electronics | luxury |
                           gambling | crypto | restaurant | fashion | digital_services
country         String    uno dei 10 paesi elencati sopra
risk_level      String    low | medium | high
                           - se category in {gambling, crypto, luxury}: pesi 20% / 35% / 45%
                           - altrimenti: pesi 70% / 25% / 5%
```

## transactions.csv (fino a 100.000 righe)

```text
transaction_id       Integer   (PK)
customer_id          Integer   (FK -> customers.customer_id)
card_id              Integer   (FK -> cards.card_id, appartenente al customer)
merchant_id          Integer   (FK -> merchants.merchant_id)
amount                Float
currency              String    sempre "EUR"
country               String    paese in cui avviene la transazione
transaction_time      Date      timestamp nell'intervallo 2026-01-01 .. 2026-06-29
channel               String    online | pos | atm
device_id             String    "DEV_<customer_id>_<1-3>" oppure "DEV_NEW_<numero>" (frode)
is_foreign_country     Integer   1 se country != customers.home_country, altrimenti 0
is_night_transaction   Integer   1 se ora della transazione < 6, altrimenti 0
risk_score            Integer   0-100, calcolato dal motore regole (vedi sotto)
status                 String    APPROVED | REVIEW | BLOCKED (derivato da risk_score)
fraud_label            Integer   1 = transazione simulata come fraudolenta (ground truth),
                                   0 = transazione legittima (probabilità di frode: 2.5%)
```

## alerts.csv (una riga per ogni transazione con stato REVIEW o BLOCKED)

```text
alert_id        Integer   (PK)
transaction_id  Integer   (FK -> transactions.transaction_id)
customer_id     Integer   (FK -> customers.customer_id)
reason          String    elenco separato da ";" tra: high_amount, night_transaction,
                           foreign_country. Se nessuna di queste si applica,
                           il valore è "risk_score_threshold"
risk_score      Integer   copia del risk_score della transazione
created_at      Date      copia del transaction_time della transazione
```

Nota importante: il campo `reason` di `alerts.csv` **non elenca tutte le regole** che hanno contribuito al risk_score (ad esempio non include `high_risk_merchant`, `flagged_card`, `new_device_online`, `high_risk_customer`), ma solo un sottoinsieme (high_amount, night_transaction, foreign_country). Va tenuto presente in fase di analisi: `reason` è parziale rispetto alla reale composizione del punteggio.

---

# Motore di valutazione del rischio (regole reali)

Il Risk Score parte da 0 e viene incrementato in base alle seguenti regole, applicate nell'ordine seguente. Il punteggio finale è troncato a un massimo di 100 (`min(risk_score, 100)`).

| Regola                                             | Condizione                                                              | Punteggio |
| --------------------------------------------------- | ------------------------------------------------------------------------ | --------: |
| Importo anomalo rispetto alla media cliente         | `amount > avg_transaction_amount * 5`                                    |       +30 |
| Transazione notturna                                | `is_night_transaction == 1` (ora < 6)                                    |       +10 |
| Paese estero                                        | `is_foreign_country == 1`                                                |       +20 |
| Merchant ad alto rischio                            | `merchant.risk_level == "high"`                                          |       +25 |
| Merchant a medio rischio                            | `merchant.risk_level == "medium"`                                        |       +10 |
| Carta segnalata (flagged)                           | `card.card_status == "flagged"`                                          |       +40 |
| Nuovo dispositivo online                            | `channel == "online"` e `device_id` inizia con `"DEV_NEW"`               |       +15 |
| Cliente ad alto rischio                             | `customer.risk_profile == "high"`                                        |       +10 |

Non esistono nel dataset reale regole basate su: soglie assolute in euro (es. "> 1.000 €"), velocity (numero di transazioni al minuto), o incompatibilità geografica calcolata da coordinate — questi concetti **non sono implementati** nel generatore e vanno trattati come possibili estensioni future, non come regole già presenti nei dati.

Il punteggio complessivo determina lo stato della transazione secondo le seguenti soglie **reali**:

```text
Risk Score < 40
    │
    ▼
APPROVED


40 <= Risk Score < 70
    │
    ▼
REVIEW


Risk Score >= 70
    │
    ▼
BLOCKED
```

Le regole e le soglie sono parametrizzabili nel motore, ma i valori sopra riportati sono quelli effettivamente usati per generare `transactions.csv` e `alerts.csv` nel dataset corrente.

---

# Simulazione delle transazioni (logica reale del generatore)

Il generatore crea transazioni in due modalità, selezionate con probabilità 2.5% (fraudolenta) / 97.5% (legittima):

## Transazione legittima (fraud_label = 0)

```text
amount          = uniforme(avg_transaction_amount * 0.2, avg_transaction_amount * 2.5)
country         = home_country del cliente (88%) oppure paese casuale (12%)
ora              = intero casuale tra 6 e 23
channel          = online (45%) | pos (50%) | atm (5%)
device_id        = "DEV_<customer_id>_<1-3>"
```

## Transazione fraudolenta (fraud_label = 1)

```text
amount          = uniforme(avg_transaction_amount * 4, avg_transaction_amount * 12)
country         = paese diverso da home_country del cliente
ora              = una tra: 0, 1, 2, 3, 4, 5, 22, 23
channel          = online (75%) | pos (20%) | atm (5%)
device_id        = "DEV_NEW_<numero casuale a 6 cifre>"
```

Nota: `fraud_label` è la **ground truth** generata direttamente dal simulatore, indipendente dal calcolo del risk_score. Il risk_score/status derivano dalle regole sopra e possono non coincidere con `fraud_label` (è proprio questo scarto a essere oggetto di valutazione tramite la confusion matrix).

## Tipologie di frode: cosa è realmente simulato

A differenza di una simulazione con scenari di frode distinti (velocity attack, account takeover, geographical anomaly, high-value transaction, card testing, multiple merchants), il generatore attuale implementa **un unico pattern combinato**, che unisce contemporaneamente: importo elevato, paese estero, orario notturno e dispositivo nuovo su canale online. Non esiste distinzione tra le diverse tipologie di frode nel dataset: ogni transazione con `fraud_label = 1` presenta simultaneamente (con variazione casuale) queste caratteristiche.

Le tipologie descritte in versioni precedenti di questo documento (Velocity Attack, Account Takeover, Geographical Anomaly, Card Testing, Multiple Merchants) rappresentano possibili estensioni sperimentali del simulatore, ma **non sono presenti nel dataset attuale** e richiederebbero modifiche a `dataset.py` (es. generazione di burst temporali per lo stesso customer_id, tracciamento di coordinate geografiche, sequenze di micro-transazioni).

---

# Ground Truth

Ogni transazione generata dal simulatore ha un'etichetta interna (`fraud_label`) che rappresenta il suo stato reale, indipendente dal risultato del motore di rischio.

```text
transaction_id | fraud_label
--------------------------------
1              | 0
2              | 0
3              | 1
4              | 0
5              | 1
```

Il sistema antifrode produce invece una decisione (`status`), calcolata dal risk_score:

```text
transaction_id | status
--------------------------------
1              | APPROVED
2              | REVIEW
3              | BLOCKED
4              | APPROVED
5              | REVIEW
```

Il confronto tra `fraud_label` (valore reale) e `status` (decisione del sistema) permette di valutare l'efficacia del sistema di rilevamento. Ai fini della confusion matrix, si può considerare "fraud predetta" lo stato `BLOCKED` (e opzionalmente anche `REVIEW`, a seconda della soglia scelta per l'analisi).

---

# Valutazione del rilevamento delle frodi

Il sistema può essere valutato attraverso una **Confusion Matrix**, confrontando `fraud_label` (ground truth) con `status` (decisione del sistema):

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

* **True Positive (TP)**: `fraud_label = 1` e `status = BLOCKED` (o REVIEW, a seconda della soglia);
* **True Negative (TN)**: `fraud_label = 0` e `status = APPROVED`;
* **False Positive (FP)**: `fraud_label = 0` ma `status` = BLOCKED/REVIEW;
* **False Negative (FN)**: `fraud_label = 1` ma `status = APPROVED`.

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

* lo stesso dataset (customers.csv, cards.csv, merchants.csv, transactions.csv);
* lo stesso flusso di transazioni;
* le stesse regole antifrode (tabella riportata sopra);
* le stesse soglie di stato (40 / 70).

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

Il confronto potrà essere organizzato attraverso tre esperimenti principali. Le dimensioni indicate sono compatibili con il volume massimo generabile da `dataset.py` (`N_TRANSACTIONS = 100.000`); per lo scenario da 1.000.000 di transazioni sarà necessario aumentare tale parametro nello script.

## Esperimento A — Carico crescente

Il sistema verrà testato con dataset di dimensioni differenti:

```text
1.000 transazioni
10.000 transazioni
100.000 transazioni      (dimensione massima nativa del generatore attuale)
1.000.000 transazioni    (richiede modifica di N_TRANSACTIONS in dataset.py)
```

Per ogni scenario verranno misurati:

* throughput;
* latenza;
* utilizzo CPU;
* utilizzo RAM;
* accuratezza del rilevamento delle frodi (confronto fraud_label vs status).

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

Verranno testati diversi livelli di complessità del motore antifrode, a partire dalle 8 regole reali attualmente implementate (vedi tabella "Motore di valutazione del rischio"):

```text
Scenario 1
3 regole antifrode (sottoinsieme delle 8 reali)

Scenario 2
8 regole antifrode (tutte quelle attualmente implementate nel dataset)

Scenario 3
30 regole antifrode (richiede estensione del risk engine)

Scenario 4
50 regole antifrode (richiede estensione del risk engine)
```

L'obiettivo sarà analizzare l'impatto della complessità della logica antifrode sulle prestazioni dei due sistemi. Gli scenari 3 e 4 richiedono l'aggiunta di nuove regole (es. velocity, geo-distanza) non presenti nel generatore attuale.

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
│   │       └── generator.py      (basato su dataset.py)
│   │
│   ├── voltdb-engine/
│   │   ├── Dockerfile
│   │   └── app/
│   │       ├── client.py
│   │       └── risk_engine.py    (implementa le 8 regole reali)
│   │
│   ├── postgres-engine/
│   │   ├── Dockerfile
│   │   └── app/
│   │       ├── client.py
│   │       └── risk_engine.py    (stessa logica di risk_engine.py sopra)
│   │
│   └── benchmark/
│       ├── Dockerfile
│       └── app/
│           ├── benchmark.py
│           └── metrics.py
│
├── database/
│   ├── voltdb/
│   │   └── schema.sql            (tabelle: customers, cards, merchants, transactions, alerts)
│   │
│   └── postgres/
│       └── schema.sql            (stesso schema)
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
* accesso frequente ai dati storici (in particolare `avg_transaction_amount` e `risk_profile` del cliente, usati direttamente nelle regole di rischio);
* applicazione di regole antifrode;
* necessità di identificare rapidamente comportamenti anomali.

Il confronto finale considererà sia gli aspetti **prestazionali** sia quelli relativi alla **qualità del rilevamento delle frodi** (confronto tra `fraud_label` e `status`), mantenendo invariata la logica antifrode — le 8 regole e le soglie 40/70 descritte in questo documento — tra le due implementazioni.
