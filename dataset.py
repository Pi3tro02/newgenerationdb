# File che si occupa della generazione del dataset

import csv
import random
from datetime import datetime, timedelta

random.seed(42)

N_CUSTOMERS = 5000
N_CARDS = 6000
N_MERCHANTS = 500
N_TRANSACTIONS = 100000

countries = [
    "Italy", "France", "Germany", "Spain", "Netherlands",
    "Belgium", "Austria", "Poland", "Romania", "United Kingdom"
]

categories = [
    "grocery", "fuel", "travel", "electronics", "luxury",
    "gambling", "crypto", "restaurant", "fashion", "digital_services"
]

channels = ["online", "pos", "atm"]
risk_profiles = ["low", "medium", "high"]
merchant_risks = ["low", "medium", "high"]
card_types = ["debit", "credit"]
card_statuses = ["active", "active", "active", "active", "flagged", "blocked"]

start_date = datetime(2026, 1, 1, 0, 0, 0)

# Metodo che genera un timestamp random
def random_timestamp():
    return start_date + timedelta(
        days=random.randint(0, 179),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59)
    )

# Metodo che definisce lo stato di una transazione in base al suo risk-score
def status_from_score(score):
    if score >= 70:
        return "BLOCKED"
    elif score >= 40:
        return "REVIEW"
    return "APPROVED"

# Clienti
customers = []

# Generazione random dei clienti nel file customers.csv
for i in range(1, N_CUSTOMERS + 1):
    customer_id = i
    home_country = random.choice(countries)
    risk_profile = random.choices(
        risk_profiles,
        weights=[0.75, 0.20, 0.05]
    )[0]

    if risk_profile == "low":
        avg_amount = round(random.uniform(20, 120), 2)
    elif risk_profile == "medium":
        avg_amount = round(random.uniform(80, 300), 2)
    else:
        avg_amount = round(random.uniform(200, 800), 2)

    created_at = datetime(2025, random.randint(1, 12), random.randint(1, 28),
                          random.randint(8, 20), random.randint(0, 59), 0)

    customers.append({
        "customer_id": customer_id,
        "name": f"Customer_{customer_id}",
        "home_country": home_country,
        "risk_profile": risk_profile,
        "avg_transaction_amount": avg_amount,
        "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S")
    })

with open("customers.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=customers[0].keys())
    writer.writeheader()
    writer.writerows(customers)


# Carte di credito
cards = []

# Generazione randomica delle carte di credito nel file cards.csv
for i in range(1, N_CARDS + 1):
    card_id = 90000 + i
    customer = random.choice(customers)
    card_type = random.choice(card_types)
    card_status = random.choices(
        ["active", "flagged", "blocked"],
        weights=[0.94, 0.05, 0.01]
    )[0]
    daily_limit = round(random.choice([500, 1000, 1500, 3000, 5000]), 2)

    cards.append({
        "card_id": card_id,
        "customer_id": customer["customer_id"],
        "card_type": card_type,
        "card_status": card_status,
        "daily_limit": daily_limit
    })

with open("cards.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=cards[0].keys())
    writer.writeheader()
    writer.writerows(cards)

# Esercenti
merchants = []

# Generazione randomica degli esercenti nel file merchants.csv
for i in range(1, N_MERCHANTS + 1):
    category = random.choice(categories)

    if category in ["gambling", "crypto", "luxury"]:
        risk_level = random.choices(
            merchant_risks,
            weights=[0.20, 0.35, 0.45]
        )[0]
    else:
        risk_level = random.choices(
            merchant_risks,
            weights=[0.70, 0.25, 0.05]
        )[0]

    merchants.append({
        "merchant_id": i,
        "merchant_name": f"Merchant_{i}",
        "category": category,
        "country": random.choice(countries),
        "risk_level": risk_level
    })

with open("merchants.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=merchants[0].keys())
    writer.writeheader()
    writer.writerows(merchants)

# Dizionari di supporto
customer_by_id = {c["customer_id"]: c for c in customers}
cards_by_customer = {}

for card in cards:
    cards_by_customer.setdefault(card["customer_id"], []).append(card)

# Transazioni
transactions = []

# Generazione randomica delle transazioni nel file transactions.csv
for transaction_id in range(1, N_TRANSACTIONS + 1):
    customer = random.choice(customers)
    customer_id = customer["customer_id"]

    customer_cards = cards_by_customer.get(customer_id)
    if not customer_cards:
        continue

    card = random.choice(customer_cards)
    merchant = random.choice(merchants)

    avg_amount = float(customer["avg_transaction_amount"])

    # 97.5% transazioni normali, 2.5% potenzialmente fraudolente
    fraud_label = 1 if random.random() < 0.025 else 0

    if fraud_label == 1:
        amount = round(random.uniform(avg_amount * 4, avg_amount * 12), 2)
        country = random.choice([c for c in countries if c != customer["home_country"]])
        hour = random.choice([0, 1, 2, 3, 4, 5, 22, 23])
        channel = random.choices(channels, weights=[0.75, 0.20, 0.05])[0]
        device_id = f"DEV_NEW_{random.randint(100000, 999999)}"
    else:
        amount = round(random.uniform(avg_amount * 0.2, avg_amount * 2.5), 2)
        country = random.choices(
            [customer["home_country"], random.choice(countries)],
            weights=[0.88, 0.12]
        )[0]
        hour = random.randint(6, 23)
        channel = random.choices(channels, weights=[0.45, 0.50, 0.05])[0]
        device_id = f"DEV_{customer_id}_{random.randint(1, 3)}"

    transaction_time = random_timestamp().replace(hour=hour)

    is_foreign_country = 1 if country != customer["home_country"] else 0
    is_night_transaction = 1 if transaction_time.hour < 6 else 0

    risk_score = 0
    reasons = []

    # Definizione delle motivazioni per il rifiuto di una transazione
    if amount > avg_amount * 5:
        risk_score += 30
        reasons.append("high_amount")

    if is_night_transaction:
        risk_score += 10
        reasons.append("night_transaction")

    if is_foreign_country:
        risk_score += 20
        reasons.append("foreign_country")

    if merchant["risk_level"] == "high":
        risk_score += 25
        reasons.append("high_risk_merchant")
    elif merchant["risk_level"] == "medium":
        risk_score += 10
        reasons.append("medium_risk_merchant")

    if card["card_status"] == "flagged":
        risk_score += 40
        reasons.append("flagged_card")

    if channel == "online" and device_id.startswith("DEV_NEW"):
        risk_score += 15
        reasons.append("new_device_online")

    if customer["risk_profile"] == "high":
        risk_score += 10
        reasons.append("high_risk_customer")

    risk_score = min(risk_score, 100)
    status = status_from_score(risk_score)

    transactions.append({
        "transaction_id": transaction_id,
        "customer_id": customer_id,
        "card_id": card["card_id"],
        "merchant_id": merchant["merchant_id"],
        "amount": amount,
        "currency": "EUR",
        "country": country,
        "transaction_time": transaction_time.strftime("%Y-%m-%d %H:%M:%S"),
        "channel": channel,
        "device_id": device_id,
        "is_foreign_country": is_foreign_country,
        "is_night_transaction": is_night_transaction,
        "risk_score": risk_score,
        "status": status,
        "fraud_label": fraud_label
    })

with open("transactions.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=transactions[0].keys())
    writer.writeheader()
    writer.writerows(transactions)

# Alert
alerts = []
alert_id = 1

# Generazione degli alert nel file alerts.csv
for t in transactions:
    if t["status"] in ["REVIEW", "BLOCKED"]:
        reason_list = []

        if float(t["amount"]) > float(customer_by_id[t["customer_id"]]["avg_transaction_amount"]) * 5:
            reason_list.append("high_amount")

        if t["is_night_transaction"] == 1:
            reason_list.append("night_transaction")

        if t["is_foreign_country"] == 1:
            reason_list.append("foreign_country")

        alerts.append({
            "alert_id": alert_id,
            "transaction_id": t["transaction_id"],
            "customer_id": t["customer_id"],
            "reason": ";".join(reason_list) if reason_list else "risk_score_threshold",
            "risk_score": t["risk_score"],
            "created_at": t["transaction_time"]
        })

        alert_id += 1

with open("alerts.csv", "w", newline="", encoding="utf-8") as f:
    fieldnames = ["alert_id", "transaction_id", "customer_id", "reason", "risk_score", "created_at"]
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(alerts)


print("Dataset generato correttamente.")
print(f"customers.csv: {len(customers)} righe")
print(f"cards.csv: {len(cards)} righe")
print(f"merchants.csv: {len(merchants)} righe")
print(f"transactions.csv: {len(transactions)} righe")
print(f"alerts.csv: {len(alerts)} righe")
