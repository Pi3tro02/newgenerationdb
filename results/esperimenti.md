# Punto 9 - Esperimenti benchmark

Data esecuzione: 2026-08-28

## Metodo

Gli esperimenti sono stati eseguiti con ambienti Docker Compose isolati e volumi nuovi per ogni run valido.
Questo evita collisioni sulle chiavi primarie di `transactions` e `alerts` senza cancellare i volumi preesistenti.

Per ogni run sono stati usati:

- stessi `transactions.csv`, `customers.csv`, `cards.csv`, `merchants.csv`;
- stesso risk engine condiviso tra PostgreSQL e VoltDB;
- target `both`, quindi stessa sequenza inviata a entrambi i motori;
- verifica finale di mismatch PostgreSQL / VoltDB.

Ogni run valido e' stato eseguito in un progetto Compose diverso (`-p ...`). In questo modo Docker ha creato volumi separati per PostgreSQL e VoltDB, mantenendo vuote le tabelle `transactions` e `alerts` all'inizio di ciascun esperimento. Questo e' importante perche' le transazioni hanno `transaction_id` fissi nel CSV: rieseguire lo stesso benchmark sullo stesso database senza pulizia produrrebbe violazioni di chiave primaria e risultati non validi.

Il run `benchmark_20260828_154244` e' stato eliminato dai risultati conservati: durante quella prova era attivo anche il simulatore, causando inserimenti duplicati e mismatch non rappresentativi.

## Comandi utilizzati

Controllo iniziale dei container:

```bash
docker compose ps
```

Avvio di un ambiente isolato per il run da 1,000 transazioni:

```bash
docker compose -p punto9 up -d postgres voltdb-init
docker compose -p punto9 logs --no-color --tail=90 voltdb-init
docker compose -p punto9 exec -T postgres psql -U fraud -d frauddb -c "SELECT 'customers' AS table_name, COUNT(*) FROM customers UNION ALL SELECT 'cards', COUNT(*) FROM cards UNION ALL SELECT 'merchants', COUNT(*) FROM merchants UNION ALL SELECT 'transactions', COUNT(*) FROM transactions UNION ALL SELECT 'alerts', COUNT(*) FROM alerts;"
docker compose -p punto9 build benchmark
docker compose -p punto9 run --rm --no-deps benchmark python services/benchmark/app/benchmark.py --target both --transactions-csv /app/transactions.csv --limit 1000 --postgres-url postgresql://fraud:fraud@postgres:5432/frauddb --voltdb-api-url http://voltdb:8080/api/2.0 --results-dir /app/results > /tmp/punto9_benchmark_1000.log
docker compose -p punto9 down
```

Avvio di un ambiente isolato per il run da 10,000 transazioni:

```bash
docker compose -p punto9a10k up -d postgres voltdb-init
docker compose -p punto9a10k logs --no-color --tail=40 voltdb-init
docker compose -p punto9a10k exec -T postgres psql -U fraud -d frauddb -c "SELECT COUNT(*) AS transactions FROM transactions;"
docker compose -p punto9a10k build benchmark
docker compose -p punto9a10k run --rm --no-deps benchmark python services/benchmark/app/benchmark.py --target both --transactions-csv /app/transactions.csv --limit 10000 --postgres-url postgresql://fraud:fraud@postgres:5432/frauddb --voltdb-api-url http://voltdb:8080/api/2.0 --results-dir /app/results > /tmp/punto9_benchmark_10000.log
docker compose -p punto9a10k down
```

Avvio degli ambienti isolati per i test TPS nominali:

```bash
docker compose -p punto9tps100 up -d postgres voltdb-init
docker compose -p punto9tps100 logs --no-color --tail=25 voltdb-init
docker compose -p punto9tps100 build benchmark
docker compose -p punto9tps100 run --rm --no-deps benchmark python services/benchmark/app/benchmark.py --target both --transactions-csv /app/transactions.csv --limit 1000 --tps 100 --postgres-url postgresql://fraud:fraud@postgres:5432/frauddb --voltdb-api-url http://voltdb:8080/api/2.0 --results-dir /app/results > /tmp/punto9_benchmark_tps100.log
docker compose -p punto9tps100 down

docker compose -p punto9tps1000 up -d postgres voltdb-init
docker compose -p punto9tps1000 logs --no-color --tail=20 voltdb-init
docker compose -p punto9tps1000 build benchmark
docker compose -p punto9tps1000 run --rm --no-deps benchmark python services/benchmark/app/benchmark.py --target both --transactions-csv /app/transactions.csv --limit 1000 --tps 1000 --postgres-url postgresql://fraud:fraud@postgres:5432/frauddb --voltdb-api-url http://voltdb:8080/api/2.0 --results-dir /app/results > /tmp/punto9_benchmark_tps1000.log
docker compose -p punto9tps1000 down

docker compose -p punto9tps5000 up -d postgres voltdb-init
docker compose -p punto9tps5000 logs --no-color --tail=20 voltdb-init
docker compose -p punto9tps5000 build benchmark
docker compose -p punto9tps5000 run --rm --no-deps benchmark python services/benchmark/app/benchmark.py --target both --transactions-csv /app/transactions.csv --limit 1000 --tps 5000 --postgres-url postgresql://fraud:fraud@postgres:5432/frauddb --voltdb-api-url http://voltdb:8080/api/2.0 --results-dir /app/results > /tmp/punto9_benchmark_tps5000.log
docker compose -p punto9tps5000 down
```

Comandi di controllo e sintesi usati dopo i run:

```bash
tail -70 /tmp/punto9_benchmark_1000.log
tail -75 /tmp/punto9_benchmark_10000.log
tail -70 /tmp/punto9_benchmark_tps100.log
tail -70 /tmp/punto9_benchmark_tps1000.log
tail -70 /tmp/punto9_benchmark_tps5000.log
find results -maxdepth 1 -type f -name 'benchmark_20260828_*' -print | sort
```

## Esperimento A - Carico crescente

| File summary | Limit | TPS | Mismatch | Errori PG | Errori VoltDB | PG avg ms | PG P95 ms | PG tx/s | VoltDB avg ms | VoltDB P95 ms | VoltDB tx/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `benchmark_20260828_154651_summary.json` | 1,000 | none | 0 | 0 | 0 | 4.613 | 7.013 | 216.792 | 20.484 | 31.159 | 48.819 |
| `benchmark_20260828_155137_summary.json` | 10,000 | none | 0 | 0 | 0 | 4.232 | 6.250 | 236.284 | 15.765 | 22.518 | 63.432 |

Nel primo esperimento il carico e' stato aumentato da 1,000 a 10,000 transazioni, senza imporre un TPS artificiale. Il benchmark misura il tempo end-to-end necessario per recuperare il contesto dal database, applicare il risk engine comune, inserire la transazione e creare l'eventuale alert.

Il risultato piu importante e' la stabilita funzionale: entrambi i run hanno `mismatch = 0` e `errori = 0`. Questo significa che PostgreSQL e VoltDB hanno assegnato lo stesso `status` (`APPROVED`, `REVIEW`, `BLOCKED`) a tutte le transazioni elaborate. Di conseguenza, le differenze osservate riguardano le prestazioni dell'implementazione e non divergenze nella logica antifrode.

Dal punto di vista prestazionale PostgreSQL e' piu veloce nella configurazione attuale. Sul run da 1,000 transazioni ha una latenza media di 4.613 ms, contro 20.484 ms di VoltDB. Sul run da 10,000 transazioni PostgreSQL scende a 4.232 ms medi, mentre VoltDB scende a 15.765 ms medi. Il miglioramento nel run piu grande puo' dipendere da warm-up del runtime, cache, connessioni gia' stabilizzate e minore incidenza dei costi iniziali sul totale.

La differenza di throughput conferma lo stesso andamento: PostgreSQL arriva a circa 216-236 tx/s, mentre VoltDB sta tra circa 49 e 63 tx/s. Questo non va letto come limite assoluto di VoltDB, perche' il client usa chiamate `@AdHoc` via JSON API e fa piu round-trip per transazione. In altre parole, il test misura l'architettura applicativa attuale, non il massimo teorico del motore VoltDB.

## Esperimento B - TPS nominale

| File summary | Limit | TPS nominale | Tempo totale s | Mismatch | PG avg ms | PG P95 ms | PG tx/s | VoltDB avg ms | VoltDB P95 ms | VoltDB tx/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `benchmark_20260828_155324_summary.json` | 1,000 | 100 | 25.414 | 0 | 4.678 | 6.589 | 213.762 | 20.431 | 28.947 | 48.945 |
| `benchmark_20260828_155454_summary.json` | 1,000 | 1,000 | 26.217 | 0 | 4.809 | 8.542 | 207.934 | 21.107 | 32.442 | 47.378 |
| `benchmark_20260828_155610_summary.json` | 1,000 | 5,000 | 24.928 | 0 | 4.624 | 7.705 | 216.253 | 20.009 | 31.981 | 49.977 |

Il secondo esperimento impone tre valori di TPS nominale: 100, 1,000 e 5,000. In teoria, 1,000 transazioni a 100 TPS richiederebbero circa 10 secondi; a 1,000 TPS circa 1 secondo; a 5,000 TPS una frazione di secondo. I tempi reali, pero', sono tutti attorno a 25-26 secondi.

Questo comportamento indica che il rate limiter non e' il fattore dominante. Il benchmark elabora ogni transazione in modo sequenziale e, per ogni transazione, deve attendere sia PostgreSQL sia VoltDB. Quando il TPS richiesto supera la capacita effettiva del pipeline, il programma non puo' accelerare oltre il tempo necessario per completare le chiamate reali. Per questo i tre run hanno throughput molto simili.

Anche in questo caso la parita funzionale e' completa: tutti i test TPS hanno mismatch pari a 0. Quindi, anche sotto carico nominale crescente, la logica antifrode rimane allineata tra i due database.

Il risultato pratico e' che l'implementazione attuale sostiene circa 200-216 tx/s lato PostgreSQL e circa 47-50 tx/s lato VoltDB nel contesto di questo benchmark sequenziale. Il throughput complessivo percepito dal benchmark `both` e' limitato soprattutto dal target piu lento, cioe' VoltDB tramite JSON API.

## Esperimento C - Ottimizzazione VoltDB con cache
Dopo i primi benchmark, VoltDB risultava penalizzato, poiché, per ogni transazione, il client recuperava il contesto cont tre query separate:

- `SELECT` su `customers`;
- `SELECT` su `cards`;
- `SELECT` su `merchants`.

A queste si aggiungevano l'inserimento della transazione e l'eventuale inserimento dell'alert. Di conseguenza, ogni transazione poteva richiedere fino a cinque round-trip verso VoltDB.

Per ridurre questo overhead, abbiamo deciso di introdurre una cache lato client, per le tabelle `customers`, `cards` e `merchants`. Esse sono statiche durante il benchmark, quindi possono essere caricate in memoria all'avvio del test. Durante l'elaborazione delle transazioni, il client recupera il contesto dalla cache invece di interrogare VoltDB ogni volta.

Nei risultati di seguito mostrati, si evince l'ottimizzazione ottenuta:

| File summary | Limit | Mismatch | Errori VoltDB | VoltDB avg base ms | VoltDB avg cached ms | Miglioramento avg | VoltDB P95 base ms | VoltDB P95 cached ms | Throughput base | Throughput cached |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `benchmark_20260828_173006_summary.json` | 1,000 | 0 | 0 | 20.484 | 8.459 | -58.7% | 31.159 | 15.004 | 48.819 | 118.219 |
| `benchmark_20260828_173359_summary.json` | 10,000 | 0 | 0 | 15.765 | 6.415 | -59.3% | 22.518 | 11.534 | 63.432 | 155.885 |

La latenza di VoltDB è scesa drasticamente:
- Sulla run da 1,000 transazioni la latenza media è passata da 20.484 ms a 8.459 ms;
- Sulla run da 10,000 transazioni da 15.765 ms a 6.415 ms;

Anche il throughput è migliorato nettamente: nella run da 10,000 transazioni VoltDb è passato da 63.432 tx/s a 155.885 tx/s. Da qui si deduce che il vero collo di bottiglia non era dato dal calcolo del risk-score, ma il numero di round-trip necessari per recuperare il conteggio dal database.

La correttezza funzionale è rimasta invariata: entrambe le run ottimizzate hanno prodotto `mismatch_count = 0` ed errori pari a 0. Le metriche di rilevamento frodi sono identiche a quelle dei benchmark precedenti.

## Metriche frodi

Nei run da 1,000 transazioni, le metriche di rilevamento sono identiche tra PostgreSQL e VoltDB:

- modalita severa, solo `BLOCKED` = frode predetta: precision 89.47%, recall 58.62%, F1 70.83%;
- modalita ampia, `REVIEW` o `BLOCKED` = frode predetta: precision 29.00%, recall 100.00%, F1 44.96%.

Dettaglio sui run da 1,000 transazioni:

- ground truth: 971 transazioni legittime e 29 frodi;
- decisioni prodotte: 900 `APPROVED`, 81 `REVIEW`, 19 `BLOCKED`;
- modalita severa: 17 TP, 969 TN, 2 FP, 12 FN;
- modalita ampia: 29 TP, 900 TN, 71 FP, 0 FN.

Nel run da 10,000 transazioni, le metriche di rilevamento sono identiche tra PostgreSQL e VoltDB:

- modalita severa: precision 83.16%, recall 68.10%, F1 74.88%;
- modalita ampia: precision 26.51%, recall 98.28%, F1 41.76%.

Dettaglio sul run da 10,000 transazioni:

- ground truth: 9,768 transazioni legittime e 232 frodi;
- decisioni prodotte: 9,140 `APPROVED`, 670 `REVIEW`, 190 `BLOCKED`;
- modalita severa: 158 TP, 9,736 TN, 32 FP, 74 FN;
- modalita ampia: 228 TP, 9,136 TN, 632 FP, 4 FN.

La modalita severa considera frode predetta solo `BLOCKED`. Questa scelta produce una precision alta: quando il sistema blocca una transazione, nella maggior parte dei casi si tratta davvero di frode. Lo svantaggio e' una recall piu bassa: alcune frodi non vengono bloccate, ma finiscono in `REVIEW` oppure, in pochi casi, in `APPROVED`.

La modalita ampia considera frode predetta sia `REVIEW` sia `BLOCKED`. Questa scelta e' piu prudente: intercetta quasi tutte le frodi, con recall 100% sui run da 1,000 e 98.28% sul run da 10,000. Lo svantaggio e' la precision piu bassa, perche' molte transazioni legittime vengono mandate in review e diventano falsi positivi.

Questa differenza e' coerente con un sistema antifrode reale: `BLOCKED` rappresenta una decisione forte, ad alta confidenza; `REVIEW` rappresenta una zona grigia in cui il sistema preferisce chiedere controllo umano invece di approvare automaticamente.

## Osservazioni

PostgreSQL risulta piu veloce nell'implementazione corrente, con latenza media circa 4-5 ms.
Nella versione iniziale VoltDB risultava più lento a causa dell'overhead della JSON API e delle query @AdHoc. Dopo l'introduzione della cache lato client, VoltDB ha ridotto sensibilmente il divario rispetto a PostgreSQL, raggiungendo prestazioni molto vicine sul run da 10.000 transazioni.

La parita funzionale e' confermata: tutti i run validi hanno `mismatch_count = 0`.

I test TPS da 100, 1,000 e 5,000 producono tempi totali simili perche il benchmark elabora ogni transazione in modo sequenziale verso PostgreSQL e VoltDB. Quando il TPS nominale supera la capacita effettiva del pipeline, il rate limiter non riesce a renderlo piu veloce: il sistema procede al massimo throughput sostenibile.

## Limiti del confronto e sviluppi futuri

I risultati ottenuti sono sufficienti per confrontare le due implementazioni sulle operazioni applicative principali: caricamento delle anagrafiche, ricezione delle transazioni, recupero del contesto, calcolo del rischio, salvataggio delle decisioni e generazione degli alert.

Il confronto va pero' interpretato come benchmark end-to-end del prototipo realizzato. La versione VoltDB usa chiamate `@AdHoc` tramite JSON API e piu round-trip per ogni transazione. Questo introduce overhead applicativo e di protocollo, penalizzando VoltDB rispetto a una possibile implementazione piu ottimizzata basata su procedure dedicate.

Un'estensione futura potrebbe quindi consistere nello spostare parte della logica di accesso ai dati in procedure VoltDB dedicate, riducendo il numero di chiamate per transazione. In quel caso il confronto misurerebbe meglio il potenziale del database in-memory, mentre i risultati attuali misurano correttamente le prestazioni del sistema sviluppato in questa fase.

Un secondo sviluppo possibile e' eseguire il benchmark sull'intero dataset disponibile, composto da 70,125 transazioni. Per questa fase sono stati scelti run da 1,000 e 10,000 transazioni piu test TPS nominali, sufficienti a mostrare sia la correttezza funzionale sia l'andamento prestazionale del prototipo.

## Conclusione

Il sistema realizzato soddisfa l'obiettivo del progetto: simula un flusso di transazioni finanziarie, applica regole antifrode in tempo reale, genera stati finali e alert, e confronta VoltDB con un database relazionale classico.

Dal punto di vista funzionale PostgreSQL e VoltDB risultano equivalenti, perche' tutti i run validi hanno prodotto `mismatch_count = 0`. Dal punto di vista prestazionale, nell'implementazione corrente PostgreSQL risulta piu efficiente, con latenze medie inferiori e throughput superiore. Dal punto di vista della qualita' del rilevamento, i due sistemi producono metriche identiche, poiche' utilizzano lo stesso risk engine condiviso.
