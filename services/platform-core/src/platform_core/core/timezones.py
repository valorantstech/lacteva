"""Which clock a business date is measured on (DEMO-014 §4).

Three timezones existed and no rule said which won:

* `organization.timezone` — DEMO-013, authoritative for business dates;
* `collection_center.timezone` — older, defaulting to `"UTC"`, read by one
  readiness check;
* nothing at all for a person.

`"UTC"` as a centre default is the dangerous part. It is a real IANA zone, so
it looks configured, and a centre created before DEMO-013 in a Kenyan dairy
claims a clock three hours from the one its milk is actually collected on. A
reader cannot tell "this centre is genuinely in UTC" from "nobody set this".

**The hierarchy, and the reason for each level:**

    organization   →  the business clock. Always set (DEMO-013 resolves it
                      from the country at onboarding) and always the answer
                      unless something more specific applies.

    collection centre → an OPTIONAL override, for the real case of a
                      cooperative that spans a border. Null means "my
                      organization's", which is what almost every centre
                      means and what none of them could previously say.

    user           →  DISPLAY ONLY. A manager travelling may want timestamps
                      in the clock on their wrist. It must never move a
                      business date: a delivery does not change which day it
                      happened on because somebody flew to London.

That last distinction is the one worth guarding. `business_timezone()` never
consults a user; `display_timezone()` is the only function that does, and
nothing that computes a date boundary may call it.
"""

from __future__ import annotations

from platform_core.core.business_time import FALLBACK_TIMEZONE
from platform_core.core.locales import is_valid_timezone

#: What a centre stores when it has no opinion. Null — not `"UTC"`, which is
#: a claim rather than an absence.
INHERIT = None


def business_timezone(
    organization_timezone: str | None,
    center_timezone: str | None = None,
) -> str:
    """The clock a business date is measured on.

    A centre overrides its organization only when it actually says something.
    Blank, null, or a zone that no longer exists all mean "inherit", because
    the alternative — a report silently drawn on a broken zone — is worse than
    one drawn on the organization's.
    """
    if center_timezone and is_valid_timezone(center_timezone):
        return center_timezone
    return organization_timezone or FALLBACK_TIMEZONE


def display_timezone(
    organization_timezone: str | None,
    user_timezone: str | None = None,
    center_timezone: str | None = None,
) -> str:
    """The clock a timestamp is SHOWN in.

    A person's preference wins here and nowhere else. If they have none, this
    is the business timezone — so by default what someone reads matches what
    the platform counted, which is the behaviour that needs no explanation.
    """
    if user_timezone and is_valid_timezone(user_timezone):
        return user_timezone
    return business_timezone(organization_timezone, center_timezone)


def describe(organization_timezone: str | None, center_timezone: str | None) -> str:
    """One line for an operator: which clock, and where it came from."""
    resolved = business_timezone(organization_timezone, center_timezone)
    source = "centre override" if resolved == center_timezone else "organization"
    return f"{resolved} ({source})"
