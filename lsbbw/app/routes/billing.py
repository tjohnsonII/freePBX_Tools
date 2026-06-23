import os
import stripe
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from app.database import get_db
from app.auth import get_current_user

router = APIRouter(prefix="/billing")

stripe.api_key       = os.environ.get("STRIPE_SECRET_KEY", "")
_WEBHOOK_SECRET      = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
_PRICE_MONTHLY       = os.environ.get("STRIPE_PRICE_MONTHLY", "price_1TkS882OWGaF3El62qfAEvrp")
_PRICE_ANNUAL        = os.environ.get("STRIPE_PRICE_ANNUAL",  "price_1TkSKF2OWGaF3El6PUjr3sBP")
_SITE_URL            = os.environ.get("SITE_URL", "https://ilovelsbbw.com")
_TRIAL_DAYS          = 7


@router.get("/checkout")
async def checkout(request: Request, plan: str = "monthly"):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/account/login", status_code=302)

    price_id = _PRICE_ANNUAL if plan == "annual" else _PRICE_MONTHLY

    session_kwargs: dict = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": f"{_SITE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url":  f"{_SITE_URL}/account/dashboard",
        "client_reference_id": str(user["id"]),
        "subscription_data": {"trial_period_days": _TRIAL_DAYS},
    }

    if user.get("stripe_customer_id"):
        session_kwargs["customer"] = user["stripe_customer_id"]
    else:
        session_kwargs["customer_email"] = user["email"]

    try:
        session = stripe.checkout.Session.create(**session_kwargs)
    except stripe.StripeError as e:
        raise HTTPException(status_code=502, detail=getattr(e, "user_message", None) or str(e))

    return RedirectResponse(session.url, status_code=303)


@router.get("/success")
async def success(request: Request, session_id: str = ""):
    # Webhook is the source of truth — this just gives users a friendly landing
    return RedirectResponse("/account/dashboard", status_code=302)


@router.post("/webhook")
async def webhook(request: Request):
    payload    = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, _WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    obj        = event["data"]["object"]

    db = get_db()
    try:
        if event_type == "checkout.session.completed":
            user_id         = obj.get("client_reference_id")
            customer_id     = obj.get("customer")
            subscription_id = obj.get("subscription")
            if user_id:
                db.execute(
                    "UPDATE users SET tier='paid', stripe_customer_id=?, stripe_subscription_id=? WHERE id=?",
                    (customer_id, subscription_id, int(user_id)),
                )
                db.commit()

        elif event_type == "customer.subscription.updated":
            customer_id = obj.get("customer")
            status      = obj.get("status")  # active, trialing, past_due, canceled, unpaid
            tier        = "paid" if status in ("active", "trialing") else "free"
            db.execute("UPDATE users SET tier=? WHERE stripe_customer_id=?", (tier, customer_id))
            db.commit()

        elif event_type == "customer.subscription.deleted":
            customer_id = obj.get("customer")
            db.execute("UPDATE users SET tier='free', stripe_subscription_id=NULL WHERE stripe_customer_id=?", (customer_id,))
            db.commit()

    finally:
        db.close()

    return {"status": "ok"}


@router.get("/portal")
async def portal(request: Request):
    user = await get_current_user(request)
    if not user or not user.get("stripe_customer_id"):
        return RedirectResponse("/account/dashboard", status_code=302)

    try:
        session = stripe.billing_portal.Session.create(
            customer=user["stripe_customer_id"],
            return_url=f"{_SITE_URL}/account/dashboard",
        )
    except stripe.StripeError as e:
        raise HTTPException(status_code=502, detail=getattr(e, "user_message", None) or str(e))

    return RedirectResponse(session.url, status_code=303)
