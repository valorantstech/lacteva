"""DEMO-013 organization locale context

An organization's country was already recorded. What it counts money in, what
clock its business days run on, and what languages its people may work in were
not — so the sales chain defaulted to the literal `"KES"`, business dates were
UTC's dates, and a user's language was a column nothing validated.

Four changes, all additive:

* `currency_code` (ISO 4217) — what this organization's money IS. Stored per
  organization rather than looked up from `country_code` on each read, because
  an organization's settings must not move when the world does: if a country
  redenominates, or the registry's principal timezone is corrected, every
  historical report of every tenant in that country would silently change
  meaning. The country is where they are; this is what they agreed to.
* `timezone` (IANA) — authoritative for business dates. Storage stays UTC.
* `supported_languages` (JSON array of BCP-47 tags) — what a user may choose.
* `default_locale` and `user_account.locale` widened to 16 characters, which
  is what `en-IN` needs and `en` did not.

**The backfill assumes nothing about anybody's money.** It maps country to
currency and timezone from a table SNAPSHOTTED HERE — a migration is a
historical record and must not change meaning when `core/locales.py` later
does. A country this snapshot does not know gets `XXX`, which is ISO 4217's
own code for "no currency involved", and `UTC`. That is deliberate: guessing
would be a guess about somebody's money, and `XXX` is absent from the currency
registry, so such an organization cannot trade until an administrator says
what it uses. Every organization in existence when this was written is `KE`,
so the fallback is theoretical — which is the point of writing it down rather
than defaulting to Kenya.

Existing behaviour is preserved exactly: `KE` organizations get `KES` and
`Africa/Nairobi`, which is what their data already contains and what the
hard-coded default already meant.

Reversible: the downgrade drops the three columns and narrows the two widened
ones back. Narrowing can only lose data if a locale tag longer than 8
characters was stored, so the downgrade truncates explicitly rather than
letting the database refuse or silently cut.
"""

import sqlalchemy as sa
from alembic import op

revision = "f3a92d18c47b"
down_revision = "e91b6c47a2d8"
branch_labels = None
depends_on = None

#: Snapshot of `core/locales.COUNTRIES` as it stood at this migration.
#: Intentionally a copy: see the module docstring.
#:
#: The languages are a PYTHON LIST, not a pre-serialized JSON string. That
#: distinction is what broke this migration the first time it met a real
#: database — see `_organization` below.
COUNTRY_LOCALES = {
    "IN": ("INR", "Asia/Kolkata", ["en-IN", "hi-IN"]),
    "KE": ("KES", "Africa/Nairobi", ["en-KE", "sw-KE"]),
    "AE": ("AED", "Asia/Dubai", ["en-AE", "ar-AE"]),
    "SA": ("SAR", "Asia/Riyadh", ["en-SA", "ar-SA"]),
    "UG": ("UGX", "Africa/Kampala", ["en-UG", "sw-UG"]),
    "TZ": ("TZS", "Africa/Dar_es_Salaam", ["en-TZ", "sw-TZ"]),
    "GB": ("GBP", "Europe/London", ["en-GB"]),
    "US": ("USD", "America/New_York", ["en-US"]),
}

#: The table as this migration needs to see it, with the REAL column types.
#:
#: The backfill was originally hand-written SQL with string bind parameters:
#:
#:     sa.text("UPDATE organization SET supported_languages = :languages ...")
#:            .bindparams(languages='["en-KE", "sw-KE"]')
#:
#: That works on SQLite, where a JSON column is TEXT and a string is exactly
#: what belongs in it. PostgreSQL refuses it at PARSE time:
#:
#:     column "supported_languages" is of type json
#:     but expression is of type character varying
#:
#: — because asyncpg sends the parameter as `text` and PostgreSQL will not
#: implicitly cast text to json in an assignment. It failed on an EMPTY
#: database, so it was never about the data.
#:
#: Declaring the column as `sa.JSON` and using a Core `update()` lets
#: SQLAlchemy render the statement for whichever dialect is actually running:
#: the JSON type's bind processor serializes the list, and the PostgreSQL
#: dialect emits the cast that PostgreSQL requires. One statement, correct on
#: both, with no dialect branch in this file.
_organization = sa.table(
    "organization",
    sa.column("country_code", sa.String),
    sa.column("currency_code", sa.String),
    sa.column("timezone", sa.String),
    sa.column("supported_languages", sa.JSON),
)


def upgrade() -> None:
    op.add_column("organization", sa.Column("currency_code", sa.String(length=3), nullable=True))
    op.add_column("organization", sa.Column("timezone", sa.String(length=64), nullable=True))
    op.add_column("organization", sa.Column("supported_languages", sa.JSON(), nullable=True))

    # Backfill before the NOT NULL, so no row is ever without a currency.
    for code, (currency, timezone, languages) in COUNTRY_LOCALES.items():
        op.execute(
            _organization.update()
            .where(sa.func.upper(_organization.c.country_code) == code)
            .values(
                currency_code=currency,
                timezone=timezone,
                supported_languages=languages,
            )
        )
    # A country this snapshot does not know: no currency, and no guess.
    op.execute(
        _organization.update()
        .where(_organization.c.currency_code.is_(None))
        .values(currency_code="XXX", timezone="UTC", supported_languages=["en"])
    )

    with op.batch_alter_table("organization") as batch:
        batch.alter_column("currency_code", existing_type=sa.String(length=3), nullable=False)
        batch.alter_column("timezone", existing_type=sa.String(length=64), nullable=False)
        batch.alter_column("supported_languages", existing_type=sa.JSON(), nullable=False)
        batch.alter_column(
            "default_locale",
            existing_type=sa.String(length=8),
            type_=sa.String(length=16),
            existing_nullable=False,
        )

    with op.batch_alter_table("user_account") as batch:
        batch.alter_column(
            "locale",
            existing_type=sa.String(length=8),
            type_=sa.String(length=16),
            existing_nullable=False,
        )


def downgrade() -> None:
    # Truncate before narrowing: PostgreSQL refuses the ALTER outright if a
    # value would not fit, which would make the downgrade fail halfway rather
    # than reverse. A locale tag cut to 8 characters is the pre-DEMO-013 shape.
    op.execute("UPDATE organization SET default_locale = substr(default_locale, 1, 8)")
    op.execute("UPDATE user_account SET locale = substr(locale, 1, 8)")

    with op.batch_alter_table("user_account") as batch:
        batch.alter_column(
            "locale",
            existing_type=sa.String(length=16),
            type_=sa.String(length=8),
            existing_nullable=False,
        )

    with op.batch_alter_table("organization") as batch:
        batch.alter_column(
            "default_locale",
            existing_type=sa.String(length=16),
            type_=sa.String(length=8),
            existing_nullable=False,
        )
    op.drop_column("organization", "supported_languages")
    op.drop_column("organization", "timezone")
    op.drop_column("organization", "currency_code")
