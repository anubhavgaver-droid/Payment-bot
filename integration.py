"""
Shared helpers (stdlib only) - copy this file into EVERY bot that sends users to the payment bot.

Flow:
  client bot  --(signed deep link)-->  payment bot  --(signed HTTP callback)-->  client bot
"""
import hmac
import hashlib
import json
import re
import urllib.request

_PAYLOAD_RE = re.compile(r"^pay-([A-Za-z0-9]{1,12})-(\d{1,6})-([A-Za-z0-9]{1,16})-([0-9a-f]{12})$")


def link_sig(secret, user_id, amount, ref):
    msg = f"{user_id}|{amount}|{ref}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:12]


def build_payload(key, secret, user_id, amount, ref):
    """Telegram /start payload (max 64 chars). key/ref: letters+digits only."""
    return f"pay-{key}-{int(amount)}-{ref}-{link_sig(secret, user_id, int(amount), ref)}"


def parse_payload(payload):
    m = _PAYLOAD_RE.match(payload or "")
    if not m:
        return None
    key, amount, ref, sig = m.groups()
    return key, int(amount), ref, sig


def verify_payload(secret, user_id, amount, ref, sig):
    return hmac.compare_digest(link_sig(secret, user_id, amount, ref), sig)


def body_sig(secret, body_bytes):
    return hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()


def post_callback(url, secret, data, timeout=15):
    """Payment bot -> client bot. Returns True only on HTTP 2xx."""
    body = json.dumps(data, separators=(",", ":")).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "X-Signature": body_sig(secret, body)},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception as e:
        print(f"Callback error: {e}")
        return False
