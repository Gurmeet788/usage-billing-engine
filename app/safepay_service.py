"""
Safepay payment gateway service.
Docs: https://getsafepay.com/docs
"""
import os
import hmac
import hashlib
import httpx
from dotenv import load_dotenv
from urllib.parse import urlencode
load_dotenv()

# ─────────────────────────────────────────────
# Config (read from .env)
# ─────────────────────────────────────────────
SAFEPAY_ENV = os.getenv("SAFEPAY_ENV", "sandbox")
SAFEPAY_API_KEY = os.getenv("SAFEPAY_API_KEY", "")          # public key  (sec_...)
SAFEPAY_SECRET_KEY = os.getenv("SAFEPAY_SECRET_KEY", "")    # server secret (hex string)
SAFEPAY_WEBHOOK_SECRET = os.getenv("SAFEPAY_WEBHOOK_SECRET", "")
SAFEPAY_CURRENCY = os.getenv("SAFEPAY_CURRENCY", "PKR")

if SAFEPAY_ENV == "production":
    SAFEPAY_BASE_URL = "https://api.getsafepay.com"
    SAFEPAY_CHECKOUT_URL = "https://getsafepay.com/checkout/pay"
else:
    SAFEPAY_BASE_URL = "https://sandbox.api.getsafepay.com"
    SAFEPAY_CHECKOUT_URL = "https://sandbox.api.getsafepay.com/checkout/pay"

# ─────────────────────────────────────────────
# Passport token (tbt) — required for checkout
# ─────────────────────────────────────────────
def get_passport_token() -> str:
    """
    Fetch a short-lived client authentication token (tbt) from Safepay's
    passport API. This token is required in the checkout URL.

    Returns:
        tbt (str): the client token string

    Raises:
        RuntimeError: if the Safepay API returns a non-200 response.
    """
    url = f"{SAFEPAY_BASE_URL}/client/passport/v1/token"

    headers = {
        "X-SFPY-MERCHANT-SECRET": SAFEPAY_SECRET_KEY,
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=10.0) as client:
        response = client.post(url, json={}, headers=headers)

    if not response.is_success:
        raise RuntimeError(
            f"Safepay passport token failed [{response.status_code}]: {response.text}"
        )

    data = response.json()
    # Safepay returns {"data": "<token_string>"} — not a nested object
    return data["data"]


# ─────────────────────────────────────────────
# Tracker creation
# ─────────────────────────────────────────────
def create_tracker(amount_pkr: int, currency: str = SAFEPAY_CURRENCY) -> dict:
    """
    Create a Safepay payment tracker.

    Args:
        amount_pkr: Amount in PKR (whole rupees). Will be converted to paisas internally.
        currency:   ISO currency code, defaults to PKR.

    Returns:
        dict with keys:
            - tracker_token (str): the tracker reference to build the checkout URL
            - checkout_url  (str): ready-to-use redirect URL for the frontend

    Raises:
        RuntimeError: if the Safepay API returns a non-200 response.
    """
    amount_paisas = amount_pkr * 100  # Safepay expects smallest currency unit

    # Step 1: Get the short-lived client token (tbt) FIRST
    tbt = get_passport_token()

    # Step 2: Initialize order tracker using Safepay's order init endpoint for hosted checkout
    url = f"{SAFEPAY_BASE_URL}/order/v1/init"

    headers = {
        "X-SFPY-MERCHANT-SECRET": SAFEPAY_SECRET_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "client": SAFEPAY_API_KEY,
        "amount": float(amount_pkr),
        "currency": currency,
        "environment": SAFEPAY_ENV,
    }

    with httpx.Client(timeout=10.0) as client:
        response = client.post(url, json=payload, headers=headers)

    if not response.is_success:
        raise RuntimeError(
            f"Safepay tracker creation failed [{response.status_code}]: {response.text}"
        )

    data = response.json()
    tracker_token = data["data"]["token"]

    params = {
        "env": SAFEPAY_ENV,
        "beacon": tracker_token,
        "tracker": tracker_token,
        "tbt": tbt,
        "source": "hosted",
        "redirect_url": "http://127.0.0.1:8000/payment/success",
        "cancel_url": "http://127.0.0.1:8000/payment/cancel",
    }

    checkout_url = f"{SAFEPAY_CHECKOUT_URL}?{urlencode(params)}"

    return {
        "tracker_token": tracker_token,
        "checkout_url": checkout_url,
    }


# ─────────────────────────────────────────────
# Webhook signature verification
# ─────────────────────────────────────────────
def verify_webhook_signature(
    payload_bytes: bytes,
    signature_header: str,
    headers: dict = None,
) -> bool:
    if not signature_header:
        print("[Safepay Webhook] Missing signature header")
        return False

    if headers:
        print("[Safepay Webhook] Incoming headers:")
        for k, v in headers.items():
            if k.lower().startswith("x-sfpy") or k.lower() in ("content-type", "user-agent"):
                print(f"  {k}: {v}")

    timestamp = ""
    if headers:
        timestamp = headers.get("x-sfpy-timestamp") or headers.get("X-SFPY-TIMESTAMP") or ""

    # Possible secrets to check
    known_secrets = [
        ("webhook_secret", SAFEPAY_WEBHOOK_SECRET),
        ("secret_key", SAFEPAY_SECRET_KEY),
        ("alt_secret_key", "580a40513a53e627103cc7d1d2eb9a8f2e1b424f25551eb018a9204785497b96"),
    ]

    # Possible messages
    messages = [("body", payload_bytes)]
    if timestamp:
        try:
            body_str = payload_bytes.decode("utf-8")
            messages.append(("timestamp.body", f"{timestamp}.{body_str}".encode("utf-8")))
            messages.append(("timestamp+body", f"{timestamp}{body_str}".encode("utf-8")))
        except Exception:
            pass

    candidates = []
    for secret_name, secret_val in known_secrets:
        if not secret_val:
            continue

        # Format 1: UTF-8 encoded secret string
        key_utf8 = secret_val.encode("utf-8")
        for msg_name, msg_bytes in messages:
            candidates.append((
                f"{secret_name} sha512 ({msg_name})",
                hmac.new(key_utf8, msg=msg_bytes, digestmod=hashlib.sha512).hexdigest()
            ))
            candidates.append((
                f"{secret_name} sha256 ({msg_name})",
                hmac.new(key_utf8, msg=msg_bytes, digestmod=hashlib.sha256).hexdigest()
            ))

        # Format 2: Hex-decoded secret bytes (if valid hex)
        try:
            key_raw = bytes.fromhex(secret_val)
            for msg_name, msg_bytes in messages:
                candidates.append((
                    f"{secret_name} fromhex sha512 ({msg_name})",
                    hmac.new(key_raw, msg=msg_bytes, digestmod=hashlib.sha512).hexdigest()
                ))
                candidates.append((
                    f"{secret_name} fromhex sha256 ({msg_name})",
                    hmac.new(key_raw, msg=msg_bytes, digestmod=hashlib.sha256).hexdigest()
                ))
        except ValueError:
            pass

    # Compare with received signature
    clean_sig = signature_header.strip().lower()
    for label, expected in candidates:
        if hmac.compare_digest(expected.lower(), clean_sig):
            print(f"[Safepay Webhook] Signature verified successfully using {label}!")
            return True

    print(f"[Safepay Webhook] Signature verification failed.")
    print(f"  Received: {signature_header} (len={len(signature_header)})")
    for label, expected in candidates[:6]:
        print(f"  Expected ({label}): {expected}")
    return False