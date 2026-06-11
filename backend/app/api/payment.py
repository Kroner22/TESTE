from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.app.auth import User, get_current_user
from backend.app.database import get_db
from backend.app.payment import (
    create_checkout_session,
    create_portal_session,
    construct_webhook_event,
    get_subscription_status,
    STRIPE_WEBHOOK_SECRET,
)

router = APIRouter(tags=["payment"])


@router.post("/api/v1/auth/upgrade")
def create_subscription(
    current_user: User = Depends(get_current_user),
):
    if current_user.plan == "paid":
        raise HTTPException(400, "Voce ja possui plano paid")

    session_id, session_url = create_checkout_session(
        customer_email=current_user.email,
    )
    return {
        "checkout_url": session_url,
        "session_id": session_id,
    }


@router.get("/api/v1/auth/portal")
def billing_portal(
    current_user: User = Depends(get_current_user),
):
    if not current_user.stripe_customer_id:
        raise HTTPException(400, "Nenhuma assinatura encontrada")

    portal_url = create_portal_session(current_user.stripe_customer_id)
    return {"portal_url": portal_url}


@router.post("/api/v1/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    if STRIPE_WEBHOOK_SECRET == "whsec_placeholder":
        return {"status": "ignored", "detail": "Webhook nao configurado"}

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = construct_webhook_event(payload, sig_header)
    except ValueError:
        raise HTTPException(400, "Invalid payload")
    except Exception:
        raise HTTPException(400, "Invalid signature")

    event_type = event.get("type")
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        customer_email = data.get("customer_details", {}).get("email")
        customer_id = data.get("customer")
        subscription_id = data.get("subscription")

        if customer_email and customer_id and subscription_id:
            user = db.query(User).filter(User.email == customer_email).first()
            if user:
                user.stripe_customer_id = customer_id
                user.stripe_subscription_id = subscription_id
                user.subscription_status = "active"
                user.plan = "paid"
                db.commit()

    elif event_type == "customer.subscription.updated":
        subscription_id = data.get("id")
        status = data.get("status")
        if subscription_id and status:
            user = db.query(User).filter(
                User.stripe_subscription_id == subscription_id
            ).first()
            if user:
                user.subscription_status = status
                if status == "active":
                    user.plan = "paid"
                elif status in ("past_due", "canceled", "unpaid"):
                    user.plan = "free"
                db.commit()

    elif event_type == "customer.subscription.deleted":
        subscription_id = data.get("id")
        if subscription_id:
            user = db.query(User).filter(
                User.stripe_subscription_id == subscription_id
            ).first()
            if user:
                user.subscription_status = "canceled"
                user.plan = "free"
                db.commit()

    return {"status": "received"}


# Also serve from a non-namespaced path for backwards compat
upgrade_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@upgrade_router.post("/upgrade")
def upgrade_plan(
    current_user: User = Depends(get_current_user),
):
    return create_subscription(current_user)


@upgrade_router.get("/portal")
def portal(
    current_user: User = Depends(get_current_user),
):
    return billing_portal(current_user)
