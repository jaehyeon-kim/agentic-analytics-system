import json
import time
import random
from datetime import datetime

# Note: This is a placeholder python script.
# Later, this logic will be fully ported into dynamic-des to natively generate Kafka telemetry.

def generate_payment():
    customer_id = random.randint(1, 100)
    transaction_id = f"txn-{int(time.time() * 1000)}-{random.randint(1000,9999)}"
    amount = round(random.uniform(20.0, 100.0), 2)
    merchant = random.choice(["Shell", "Chevron", "Exxon", "BP", "Mobil"])
    timestamp = datetime.utcnow().isoformat()
    return {
        "transaction_id": transaction_id,
        "customer_id": customer_id,
        "amount": amount,
        "merchant": merchant,
        "timestamp": timestamp,
        "transaction_type": "fuel_purchase"
    }

if __name__ == "__main__":
    print("Starting local payment data generation for Lab 1")
    while True:
        payment = generate_payment()
        print(json.dumps(payment))
        time.sleep(1)
