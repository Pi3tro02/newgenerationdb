# Sistema Antifrode Finanziaria Real-Time con VoltDB

## Obiettivo del progetto

Il progetto ha come obiettivo la realizzazione di un sistema di **rilevamento delle frodi finanziarie in tempo reale**, basato su **VoltDB** e sviluppato interamente in **Python**.

Il sistema simula un flusso continuo di transazioni finanziarie, replicando la logica del generatore `dataset.py`. Ogni transazione viene analizzata in tempo reale attraverso un insieme di **regole di rischio**, al fine di determinare uno stato finale:

* **APPROVED**
* **REVIEW**
* **BLOCKED**

Il progetto include inoltre un confronto sperimentale tra VoltDB e il **database relazionale tradizionale** PostgreSQL, valutando sia le prestazioni operative sia l'efficacia nel rilevamento delle transazioni fraudolente. Il confronto considera anche aspetti qualitativi, come facilità d'uso, integrazione con Python, strumenti di supporto e complessità operativa.

---

## Architettura generale

L'architettura realizzata è la seguente:

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

La logica antifrode è stata estratta in un modulo comune (`services/common/risk_engine.py`) usato sia dal client PostgreSQL sia dal client VoltDB. In questo modo le differenze osservate nei benchmark dipendono dall'architettura di accesso ai dati e dai database utilizzati, non da differenze accidentali nelle regole.

Nella prima versione il client VoltDB recuperava il contesto della transazione con query `@AdHoc` via JSON API per ogni operazione. Dopo i primi risultati sperimentali è stata introdotta anche una versione ottimizzata tramite cache lato client: le tabelle anagrafiche `customers`, `cards` e `merchants` vengono precaricate in memoria all'avvio del benchmark, riducendo il numero di round-trip verso VoltDB durante l'elaborazione dello stream.

---

## Flusso di elaborazione

Il sistema segue il seguente flusso:

```text
1. Generazione della transazione
              │
              ▼
2. Inserimento nel database
              │
              ▼
3. Recupero del contesto cliente/carta/merchant
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

Nel caso VoltDB ottimizzato, il punto 3 viene eseguito leggendo il contesto dalla cache applicativa invece di interrogare ogni volta il database. Restano invece persistenti su VoltDB gli inserimenti delle transazioni elaborate e degli alert generati.

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

## transactions.csv (70.125 righe nel dataset corrente)

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

Nota: `dataset.py` tenta di generare fino a 100.000 transazioni, ma il dataset corrente contiene 70.125 righe perché alcune iterazioni scelgono clienti senza carte associate e vengono quindi saltate. Questo comportamento è coerente con la generazione casuale delle carte, in cui un cliente può avere più carte oppure nessuna.

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

Le principali metriche sono:

* **True Positive (TP)**: `fraud_label = 1` e `status = BLOCKED` (o REVIEW, a seconda della soglia);
* **True Negative (TN)**: `fraud_label = 0` e `status = APPROVED`;
* **False Positive (FP)**: `fraud_label = 0` ma `status` = BLOCKED/REVIEW;
* **False Negative (FN)**: `fraud_label = 1` ma `status = APPROVED`.

Da questi valori vengono calcolate:

* Precision;
* Recall;
* F1-Score;
* False Positive Rate;
* False Negative Rate.

---

# Confronto VoltDB vs PostgreSQL

Il progetto confronta:

1. **VoltDB**
2. **PostgreSQL**

Entrambi i sistemi elaborano:

* lo stesso dataset (customers.csv, cards.csv, merchants.csv, transactions.csv);
* lo stesso flusso di transazioni;
* le stesse regole antifrode (tabella riportata sopra);
* le stesse soglie di stato (40 / 70).

In questo modo è possibile isolare maggiormente l'impatto del database e dell'architettura di accesso ai dati sulle prestazioni del sistema.

| Aspetto                 | VoltDB   | PostgreSQL |
| ----------------------- | -------- | ---------- |
| Inserimento transazioni | ✓        | ✓          |
| Elaborazione real-time  | ✓        | ✓          |
| Valutazione del rischio | ✓        | ✓          |
| Accesso allo storico    | ✓        | ✓          |
| Throughput              | Misurato | Misurato   |
| Latenza                 | Misurata | Misurata   |
| CPU                     | Non misurata nel benchmark finale | Non misurata nel benchmark finale |
| RAM                     | Non misurata nel benchmark finale | Non misurata nel benchmark finale |
| Rilevamento frodi       | Misurato | Misurato   |
| Scalabilità             | Valutata tramite carico crescente e TPS nominale | Valutata tramite carico crescente e TPS nominale |

## Confronto qualitativo

Oltre alle metriche numeriche, il progetto valuta anche alcuni aspetti qualitativi richiesti dall'ambito applicativo.

| Aspetto | PostgreSQL | VoltDB |
| ------- | ---------- | ------ |
| Facilità di installazione | Più semplice e immediata, soprattutto tramite Docker e strumenti standard | Più specialistico, richiede maggiore attenzione a porte, container e caricamento schema |
| Modellazione dati | Molto naturale per tabelle relazionali con chiavi primarie ed esterne | Simile a livello tabellare, ma richiede attenzione al partizionamento |
| Integrazione con Python | Diretta tramite `psycopg2` | Realizzata tramite JSON API; più codice necessario per chiamate e parsing |
| Debug e interrogazione | Comodo tramite `psql` e SQL standard | Possibile tramite `sqlcmd` e JSON API, ma meno immediato nel prototipo |
| Supporto e documentazione | Ecosistema maturo e molto diffuso | Più orientato a casi specifici real-time/in-memory |
| Prestazioni osservate | Migliori nella versione base del confronto | Penalizzato nella versione base, molto migliorato con cache lato client |
| Adeguatezza real-time | Buona nel prototipo realizzato | Coerente con scenari real-time, ma richiede un accesso ai dati ottimizzato |

Dal punto di vista pratico PostgreSQL è risultato più semplice da usare e integrare. VoltDB ha richiesto più attenzione nella configurazione e nell'accesso ai dati, ma l'ottimizzazione con cache ha mostrato che parte del divario iniziale era dovuta all'architettura applicativa scelta, non solo al database.

---

# Metriche prestazionali

Per ogni transazione vengono registrati:

```text
timestamp_inizio
timestamp_fine
latency
status
eventuale errore
```

La latenza viene calcolata come:

```text
latency = timestamp_fine - timestamp_inizio
```

Le principali metriche sono:

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

# Esperimenti eseguiti

Il confronto è stato organizzato in tre gruppi principali di esperimenti: carico crescente, TPS nominale e ottimizzazione VoltDB con cache. I risultati dettagliati sono documentati in `results/esperimenti.md`.

## Esperimento A - Carico crescente

Il sistema è stato testato con:

```text
1.000 transazioni
10.000 transazioni
```

Risultati principali:

| Run | PostgreSQL avg | PostgreSQL P95 | PostgreSQL tx/s | VoltDB avg | VoltDB P95 | VoltDB tx/s | Mismatch |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.000 tx | 4.613 ms | 7.013 ms | 216.792 | 20.484 ms | 31.159 ms | 48.819 | 0 |
| 10.000 tx | 4.232 ms | 6.250 ms | 236.284 | 15.765 ms | 22.518 ms | 63.432 | 0 |

Nella versione base PostgreSQL risulta più veloce. VoltDB è penalizzato dall'uso di più chiamate `@AdHoc` via JSON API per ogni transazione.

## Esperimento B - TPS nominale

Sono stati testati tre valori di TPS nominale su 1.000 transazioni:

```text
100 TPS
1.000 TPS
5.000 TPS
```

Risultati principali:

| TPS nominale | Tempo totale | PostgreSQL tx/s | VoltDB tx/s | Mismatch |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 25.414 s | 213.762 | 48.945 | 0 |
| 1.000 | 26.217 s | 207.934 | 47.378 | 0 |
| 5.000 | 24.928 s | 216.253 | 49.977 | 0 |

I tempi totali sono simili perché il benchmark elabora le transazioni in modo sequenziale e deve attendere entrambi i sistemi. Quando il TPS nominale supera la capacità effettiva del pipeline, il sistema procede al massimo throughput sostenibile.

## Esperimento C - Ottimizzazione VoltDB con cache

L'ottimizzazione VoltDB consiste nel precaricare in memoria `customers`, `cards` e `merchants`, evitando tre query di contesto per ogni transazione. Questa scelta è coerente con il dominio applicativo, perché tali tabelle rappresentano anagrafiche relativamente statiche durante il benchmark.

Confronto VoltDB base vs VoltDB con cache:

| Run | VoltDB avg base | VoltDB avg cache | Miglioramento avg | VoltDB P95 base | VoltDB P95 cache | Throughput base | Throughput cache | Mismatch cache |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.000 tx | 20.484 ms | 8.459 ms | -58.7% | 31.159 ms | 15.004 ms | 48.819 | 118.219 | 0 |
| 10.000 tx | 15.765 ms | 6.415 ms | -59.3% | 22.518 ms | 11.534 ms | 63.432 | 155.885 | 0 |

L'ottimizzazione riduce sensibilmente il divario rispetto a PostgreSQL. Sul run da 10.000 transazioni, PostgreSQL ha registrato una latenza media di 6.129 ms e VoltDB con cache 6.415 ms, con throughput rispettivamente pari a 163.159 tx/s e 155.885 tx/s.

## Risultati di rilevamento frodi

Le metriche di rilevamento frodi sono identiche tra PostgreSQL e VoltDB, perché entrambi usano lo stesso risk engine.

Nel run da 1.000 transazioni:

| Modalità | Precision | Recall | F1 |
| -------- | --------: | -----: | -: |
| Severa (`BLOCKED`) | 89.47% | 58.62% | 70.83% |
| Ampia (`REVIEW` + `BLOCKED`) | 29.00% | 100.00% | 44.96% |

Nel run da 10.000 transazioni:

| Modalità | Precision | Recall | F1 |
| -------- | --------: | -----: | -: |
| Severa (`BLOCKED`) | 83.16% | 68.10% | 74.88% |
| Ampia (`REVIEW` + `BLOCKED`) | 26.51% | 98.28% | 41.76% |

La modalità severa è più precisa ma intercetta meno frodi; la modalità ampia intercetta quasi tutte le frodi ma genera più falsi positivi. Questo rappresenta un compromesso realistico nei sistemi antifrode.

---

# Architettura Docker

Il progetto è organizzato tramite Docker Compose.

La struttura principale è:

```text
fraud-detection/
│
├── docker-compose.yml
│
├── services/
│   │
│   ├── simulator/
│   │   └── simulator.py          (wrapper del simulatore)
│   │
│   ├── voltdb-engine/
│   │   └── app/
│   │       ├── client.py         (client VoltDB base + cache)
│   │       ├── stream.py
│   │       └── simulator.py
│   │
│   ├── postgres-engine/
│   │   └── app/
│   │       ├── client.py
│   │       └── risk_engine.py    (wrapper di compatibilità)
│   │
│   ├── common/
│   │   └── risk_engine.py        (logica antifrode condivisa)
│   │
│   └── benchmark/
│       └── app/
│           ├── benchmark.py
│           └── metrics.py
│
├── database/
│   ├── voltdb/
│   │   ├── schema.sql
│   │   └── load_data.sql
│   │
│   └── postgres/
│       ├── 01-schema.sql
│       └── 02-load_data.sql
│
├── results/
│
└── README.md
```

L'architettura Docker finale è composta dai seguenti servizi:

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

L'ambiente può essere avviato tramite:

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

Il confronto finale considera sia gli aspetti **prestazionali** sia quelli relativi alla **qualità del rilevamento delle frodi** (confronto tra `fraud_label` e `status`), mantenendo invariata la logica antifrode — le 8 regole e le soglie 40/70 descritte in questo documento — tra le due implementazioni.

---

# Conclusione sintetica

Il sistema realizzato soddisfa l'obiettivo applicativo: costruisce un dataset finanziario sintetico, simula un flusso di transazioni, applica regole antifrode, genera stati finali e alert, e confronta VoltDB con PostgreSQL.

Dal punto di vista funzionale, PostgreSQL e VoltDB risultano equivalenti nei benchmark validi (`mismatch_count = 0`). Dal punto di vista prestazionale, PostgreSQL è più veloce nella versione base, mentre VoltDB migliora sensibilmente dopo l'introduzione della cache lato client. Dal punto di vista del rilevamento frodi, i due sistemi ottengono metriche identiche perché condividono la stessa logica di valutazione.

I principali limiti del prototipo sono l'uso iniziale di query `@AdHoc` via JSON API per VoltDB, l'assenza di procedure VoltDB dedicate, il benchmark sequenziale e la presenza di un unico pattern combinato di frode nel dataset. Questi aspetti rappresentano possibili sviluppi futuri, insieme all'estensione del generatore con scenari come velocity attack, card testing e anomalie geografiche più complesse.
