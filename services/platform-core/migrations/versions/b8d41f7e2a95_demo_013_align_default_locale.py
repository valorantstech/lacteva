"""DEMO-013 align default_locale with supported_languages

Found by running `infra/ci/reconcile_localization.py` against PRODUCTION
immediately after deploying `f3a92d18c47b`.

That migration back-filled `supported_languages` from the country registry —
`["en-KE", "sw-KE"]` for a Kenyan dairy — and left `default_locale` at
whatever it already held, which for every organization in existence was the
bare `en`. The result is a row that contradicts itself: an organization
defaulting to a language it does not list as supported.

**That is not cosmetic. It breaks the settings screen.**
`OrganizationService.update_locale_settings` validates through the same
`core/locales.resolve` that onboarding uses, and `resolve` refuses a default
language that is not among the supported ones — correctly, since an
organization cannot default to a language it has not enabled. So an
administrator on any pre-existing tenant could not change their currency,
timezone or languages at all: every attempt returned 422 about a value they
had never set.

The fix preserves the LANGUAGE and repairs the TAG. An organization defaulting
to `en` with `["en-KE", "sw-KE"]` available means English, and `en-KE` is
English — so the first supported tag whose base language matches the current
default is chosen. Nobody's language changes; the row stops contradicting
itself.

Where no supported tag shares the base language — impossible today, since
every country in the registry lists English first, but not guaranteed for a
country added later — the first supported tag wins. That is the same rule
`resolve()` applies when a caller supplies no default at all.

Deliberately NOT touching `user_account.locale`. A person's stored preference
is theirs; DEMO-013's rule is that narrowing an organization's languages never
rewrites a user's choice, and negotiation falls back at render time. This
migration is about the ORGANIZATION's own self-consistency.

Reversible in the only sense that matters: the downgrade restores the bare
base language (`en-KE` → `en`), which is the state before this ran.
"""

import sqlalchemy as sa
from alembic import op

revision = "b8d41f7e2a95"
down_revision = "f3a92d18c47b"
branch_labels = None
depends_on = None

_organization = sa.table(
    "organization",
    sa.column("id", sa.Uuid),
    sa.column("default_locale", sa.String),
    sa.column("supported_languages", sa.JSON),
)


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(
            _organization.c.id,
            _organization.c.default_locale,
            _organization.c.supported_languages,
        )
    ).all()

    for org_id, default, supported in rows:
        languages = list(supported or [])
        if not languages or default in languages:
            continue
        base = (default or "").split("-", 1)[0].lower()
        # The same language, correctly tagged — or, failing that, the first
        # language the organization actually enabled.
        aligned = next(
            (tag for tag in languages if tag.split("-", 1)[0].lower() == base),
            languages[0],
        )
        connection.execute(
            _organization.update()
            .where(_organization.c.id == org_id)
            .values(default_locale=aligned)
        )


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.select(_organization.c.id, _organization.c.default_locale)).all()
    for org_id, default in rows:
        base = (default or "en").split("-", 1)[0].lower()
        connection.execute(
            _organization.update().where(_organization.c.id == org_id).values(default_locale=base)
        )
