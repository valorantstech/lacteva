"""The plan catalog (DEMO-026).

**A registry, not a table**, for the reason the platform states everywhere
else: registries before code, and a plan is a decision the product makes rather
than data a tenant owns. A `subscription_plan` table would have to be
platform-global, which means an RLS exemption and a policy hole to explain —
paid for nothing, because no tenant may define a plan.

**No price appears here, and that is deliberate.** The commercial decision made
so far is the SHAPE: a 30-day trial, subscription per collection centre, not
per user and not per litre. The actual INR/KES/QAR numbers are a commercial
question nobody has answered yet, so inventing them in source would be inventing
a fact. A deployment that has decided sets them in the existing configuration
store, per currency, and `price_for` reads them.

That also keeps the platform country-neutral: the currency comes from the
organization the country registry configured at onboarding, never from a branch
in this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Centre allowance meaning "as many as you like". Used by the trial, because
#: the commercial model is that everything is available during the trial —
#: a dairy evaluating the platform must not meet a wall it has not been asked
#: to pay past.
UNLIMITED = -1


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    #: `month` | `year`. What one billing cycle is; nothing here charges.
    billing_period: str
    #: How many collection centres the plan covers. `UNLIMITED` for the trial.
    included_centres: int
    #: Whether a subscription on this plan may be paid for at all. The trial
    #: cannot: it has no price and no provider.
    billable: bool
    #: Capability keys this plan grants. Empty means "everything the platform
    #: has" — Lacteva does not sell modules today, and pretending it does
    #: would be a pricing page written in Python.
    capabilities: tuple[str, ...] = field(default_factory=tuple)


TRIAL = Plan(
    code="LACTEVA_TRIAL",
    name="Lacteva Trial",
    billing_period="month",
    included_centres=UNLIMITED,
    billable=False,
)

STANDARD = Plan(
    code="LACTEVA_STANDARD",
    name="Lacteva Standard",
    billing_period="month",
    #: Zero INCLUDED — a standard subscription covers exactly the centres it
    #: subscribes for, which is what "priced per collection centre" means. The
    #: quantity lives on the subscription, not on the plan.
    included_centres=0,
    billable=True,
)

PLANS: dict[str, Plan] = {plan.code: plan for plan in (TRIAL, STANDARD)}

#: Configuration key holding a plan's price in one currency:
#: `subscription.price.LACTEVA_STANDARD.INR`. Absent until somebody decides.
PRICE_CONFIG_PREFIX = "subscription.price."


def get_plan(code: str) -> Plan:
    plan = PLANS.get(code)
    if plan is None:
        raise KeyError(f"unknown plan: {code}")
    return plan


def price_config_key(plan_code: str, currency_code: str) -> str:
    """Where a deployment records what this plan costs in this currency."""
    return f"{PRICE_CONFIG_PREFIX}{plan_code}.{currency_code}"
