import os
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority")

client = MongoClient(MONGO_URI)
db = client["fampay_test_bot_db"]
settings_col = db["bot_settings"]

DEFAULT_SETTINGS = {
    "_id": "config",
    "gmail_user": "your_email@gmail.com",
    "gmail_pass": "your_gmail_app_password",
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
