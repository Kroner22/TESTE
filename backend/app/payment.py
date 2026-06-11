import os
from typing import Optional

import stripe

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_placeholder")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "price_placeholder")
DOMAIN = os.getenv("DOMAIN", "http://localhost:8000")

stripe.api_key = STRIPE_SECRET_KEY

MONTHLY_PRICE_CENTS = 4997  # R$49,97


def create_checkout_session(
    customer_email: str,
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
) -> tuple[str, str]:
    if STRIPE_SECRET_KEY == "sk_test_placeholder":
        return ("cs_simulado", f"{DOMAIN}/app/#/dashboard?upgrade=success&simulated=1")
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        customer_email=customer_email,
        success_url=success_url or f"{DOMAIN}/app/#/dashboard?upgrade=success",
        cancel_url=cancel_url or f"{DOMAIN}/app/#/dashboard?upgrade=cancel",
    )
    return session.id, session.url


def create_portal_session(customer_id: str) -> str:
    if STRIPE_SECRET_KEY == "sk_test_placeholder":
        return f"{DOMAIN}/app/#/dashboard?portal=simulated"
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{DOMAIN}/app/#/dashboard",
    )
    return session.url


def construct_webhook_event(payload: bytes, sig_header: str):
    return stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)


def get_subscription_status(subscription_id: str) -> str:
    sub = stripe.Subscription.retrieve(subscription_id)
    return sub.status
