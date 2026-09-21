from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.exceptions import APIError

from .models import Plan, Subscription, SubscriptionStatus


class PlanLimitReached(APIError):
    status_code = 402
    default_code = "PLAN_LIMIT_REACHED"
    default_detail = "This store has used its plan's order allowance."


def default_plan():
    plan = Plan.objects.filter(is_default=True, is_active=True).first()
    if plan is None:
        plan = Plan.objects.filter(is_active=True).order_by(
            "sort_order", "monthly_price"
        ).first()
    return plan


def get_or_create_subscription(store):
    subscription = Subscription.objects.filter(store=store).first()
    if subscription is not None:
        return roll_period_if_needed(subscription)

    plan = default_plan()
    if plan is None:
        return None

    today = timezone.localdate()
    return Subscription.objects.create(
        store=store,
        plan=plan,
        period_start=today,
        period_end=today + timedelta(days=30),
    )


@transaction.atomic
def roll_period_if_needed(subscription):
    if not subscription.period_expired():
        return subscription

    locked = Subscription.objects.select_for_update().get(pk=subscription.pk)
    if not locked.period_expired():
        return locked

    today = timezone.localdate()
    locked.period_start = today
    locked.period_end = today + timedelta(days=30)
    locked.orders_used = 0
    locked.save(
        update_fields=["period_start", "period_end", "orders_used", "updated_at"]
    )
    return locked


def check_order_allowance(store):
    subscription = get_or_create_subscription(store)
    if subscription is None or not subscription.is_active:
        return None

    if subscription.is_over_limit:
        raise PlanLimitReached(
            (
                f"The {subscription.plan.name} plan allows "
                f"{subscription.plan.order_limit} orders per period and this "
                "store has used them all. Upgrade to keep taking orders."
            ),
            details={
                "plan": subscription.plan.code,
                "order_limit": subscription.plan.order_limit,
                "orders_used": subscription.orders_used,
                "period_end": str(subscription.period_end),
            },
        )
    return subscription


def record_order(store):
    subscription = get_or_create_subscription(store)
    if subscription is None:
        return None

    Subscription.objects.filter(pk=subscription.pk).update(
        orders_used=F("orders_used") + 1
    )
    subscription.refresh_from_db(fields=["orders_used"])
    return subscription


def check_staff_allowance(store):
    from apps.stores.models import StoreMembership

    subscription = get_or_create_subscription(store)
    if subscription is None:
        return None

    active = StoreMembership.objects.filter(
        store=store, is_active=True
    ).count()
    if active >= subscription.plan.staff_limit:
        raise PlanLimitReached(
            (
                f"The {subscription.plan.name} plan allows "
                f"{subscription.plan.staff_limit} user(s). Upgrade to add more."
            ),
            code="PLAN_STAFF_LIMIT_REACHED",
            details={
                "plan": subscription.plan.code,
                "staff_limit": subscription.plan.staff_limit,
                "active_members": active,
            },
        )
    return subscription


@transaction.atomic
def activate_plan(store, plan, *, actor=None, reference="", note=""):
    subscription = get_or_create_subscription(store)
    today = timezone.localdate()

    if subscription is None:
        subscription = Subscription.objects.create(store=store, plan=plan)

    subscription.plan = plan
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.period_start = today
    subscription.period_end = today + timedelta(days=30)
    subscription.orders_used = 0
    subscription.activated_by = actor
    subscription.payment_reference = reference
    subscription.note = note
    subscription.save()
    return subscription


def usage_summary(store):
    subscription = get_or_create_subscription(store)
    if subscription is None:
        return None

    return {
        "plan": {
            "code": subscription.plan.code,
            "name": subscription.plan.name,
            "monthly_price": str(subscription.plan.monthly_price),
            "order_limit": subscription.plan.order_limit,
            "staff_limit": subscription.plan.staff_limit,
            "allows_api_courier": subscription.plan.allows_api_courier,
        },
        "status": subscription.status,
        "period_start": subscription.period_start,
        "period_end": subscription.period_end,
        "orders_used": subscription.orders_used,
        "orders_remaining": subscription.orders_remaining,
        "usage_percent": subscription.usage_percent,
        "is_near_limit": subscription.is_near_limit,
        "is_over_limit": subscription.is_over_limit,
    }
