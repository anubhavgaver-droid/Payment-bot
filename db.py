import os
from datetime import datetime, timedelta
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority")

client = MongoClient(MONGO_URI)
db = client["fampay_test_bot_db"]
settings_col = db["bot_settings"]
payments_col = db["payments"]  # one doc per received payment, _id = UTR (so a UTR can exist only once)

DEFAULT_SETTINGS = {
    "_id": "config",
    "upi_id": "fampay.merchant@okaxis",
    "upi_name": "Anubhav Store",
    "gateway_name": "FamPay / Pocket UPI"
}

def get_settings():
    config = settings_col.find_one({"_id": "config"})
    if not config:
        settings_col.insert_one(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS
    return config

def update_setting(key, value):
    settings_col.update_one(
        {"_id": "config"},
        {"$set": {key: value}},
        upsert=True
    )

# ================= PAYMENTS (filled by MacroDroid webhook) =================
def save_payment(utr, amount, raw_text=""):
    """Store a received payment. Returns False if this UTR was already saved."""
    try:
        payments_col.insert_one({
            "_id": utr,
            "amount": float(amount),
            "received_at": datetime.utcnow(),
            "used": False,
            "raw": (raw_text or "")[:300],
        })
        return True
    except DuplicateKeyError:
        return False

def claim_payment(utr, amount, user_id, order_id, order_created_utc):
    """
    One-time UTR claim. Returns one of:
    ok | not_found | used | amount_mismatch | old
    The final update is atomic, so two users can never claim the same UTR.
    """
    doc = payments_col.find_one({"_id": utr})
    if not doc:
        return "not_found"
    if doc.get("used"):
        return "used"
    if float(doc["amount"]) != float(amount):
        return "amount_mismatch"
    # payment must have arrived after this order was created (2 min clock margin)
    if doc["received_at"] < order_created_utc - timedelta(minutes=2):
        return "old"
    res = payments_col.find_one_and_update(
        {"_id": utr, "used": False},
        {"$set": {
            "used": True,
            "used_by": user_id,
            "order_id": order_id,
            "used_at": datetime.utcnow(),
        }}
    )
    return "ok" if res else "used"
