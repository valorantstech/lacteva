---
id: LOCALIZATION
title: Country, Currency, Timezone and Language
type: reference
status: Approved
version: "1.0"
owner: Engineering
created: 2026-08-14
last-updated: 2026-08-14
related: [MOBILE-EXPERIENCES, NOTIFICATION-ENGINE, BR-REGISTER, CLAUDE-CONTEXT]
baseline: ARCH-BASELINE-V1
---

# Country, Currency, Timezone and Language

How Lacteva serves dairies in more than one country without knowing which country it is in. Established by DEMO-013.

**The guarantee:** no application code branches on a tenant's country. A tenant's country resolves, once, to a currency, a timezone and a set of languages; everything else reads those. Adding a country is a data entry, never a code path.

## 1. Where each fact lives

| Fact | Owner | Standard |
| --- | --- | --- |
| Country | `organization.country_code` | ISO 3166-1 alpha-2 |
| Currency | `organization.currency_code` | ISO 4217 |
| Business timezone | `organization.timezone` | IANA |
| Languages offered | `organization.supported_languages` | BCP-47 |
| Organization default language | `organization.default_locale` | BCP-47 |
| **A person's** language | `user_account.locale` | BCP-47 |

The split on the last two rows is the point of §5 in the work order: the organization decides which languages it *operates in*; a person chooses their own from that list. A user may not select a language the organization has not enabled, and narrowing the organization's list does not rewrite anybody's stored preference — negotiation falls back at render time instead. An administrator editing other people's preferences from a settings form is not recoverable when the language is switched back on.

## 2. The registry, and why it is code

`core/locales.py` holds countries, currencies and languages. It is code, not a table, for the same reason permissions and `BUS_EVENTS` are: this is **reference** data — it changes when the world changes, not when a tenant does — and a typo should be a failing build rather than a row somebody has to notice. A table would need seeding, a migration per addition, and an RLS decision, and would still be edited by an engineer.

It is deliberately small. A hundred unused countries would be a hundred unverified claims about other people's currencies.

**A country the registry has never met is still onboardable.** `resolve()` requires the caller to supply currency and timezone explicitly in that case. It never guesses: guessing would be a guess about somebody's money, wrong silently, discovered on the first bill.

```
country → resolve() → {currency, timezone, default language, supported languages}
                ↑
        every part overridable
```

Overridable because the registry knows a country's *principal* timezone and a country is not always one zone, and because a tenant may run its books in a currency other than its country's. A country proposes; an organization decides.

## 3. Settings are columns, not lookups

An organization's currency and timezone are stored, not derived from `country_code` on each read. If they were derived, a correction to the registry — a redenomination, a fixed principal timezone — would silently change the meaning of every historical report of every tenant in that country. The country is where they are; the columns are what they agreed to.

Changing them goes through `organization.settings.manage`, a permission separate from the platform's `organization.manage` (which is the authority to create organizations at all) and from `configuration.write` (a deployment may let an operations lead edit configuration without letting them redenominate the books). Country is not changeable through settings: moving an organization between countries is a migration, not a setting.

## 4. Time

**Storage stays UTC.** Every timestamp column is `DateTime(timezone=True)`, `utcnow()` still stamps rows, and a canonical instant is the only thing that survives a server move or a restore into another region.

**Interpretation is the organization's.** A day is not an interval of UTC; it is an interval of somebody's local calendar, and which somebody is a business fact:

- a delivery round at 05:00 in Bengaluru is 23:30 UTC *the day before* — so a platform that asks UTC what day it is files the round under yesterday, and at a month boundary bills it in the previous month;
- the same round in Nairobi is 02:00 UTC the same day, which is why this never showed in the Kenyan demo and would have shown on the first Indian customer's first morning.

`core/business_time.py` is the decision. Day bounds are **half-open** (`[00:00, next 00:00)`) so a delivery at exactly midnight belongs to exactly one day, and are built by localizing midnight rather than adding 24 hours — a day is 23 or 25 hours across a DST transition, and Europe/London is in the registry.

It also decides which rate card prices a collection. That read the UTC date, so milk poured at dawn in India would have been priced against yesterday's card and the farmer paid the old rate, with nothing anywhere looking wrong.

**Never the client's clock.** A phone cannot compute an IANA calendar date without shipping a timezone database, and a handset on the wrong setting — or a rider who has crossed a border — must not move a dairy's accounting day. So `/v1/deliveries/report` takes **optional** dates and defaults to the organization's today, the mobile app omits them, and the platform echoes the dates it used.

## 5. Money

Currency comes from the organization and is stored on every money row, so a record always says what it is denominated in. `tenant_currency()` **raises** for an organization with no usable currency rather than defaulting: a report in the wrong timezone is a wrong report, but an invoice in a currency nobody chose is worse than no invoice.

The `default="KES"` that used to sit on five columns is gone. A code path that forgets to pass a currency now fails loudly instead of minting Kenyan shillings in an Indian dairy.

**No conversion.** DEMO-013 determines an organization's currency; it does not implement FX. Money remains `Decimal` end to end, `Numeric` in the database, and an exact decimal string on the wire — the portal formats it in string space and the mobile app never parses it into a `double`.

## 6. Translation

Three catalogs, one shape:

| Where | What | Fallback |
| --- | --- | --- |
| Backend | `core/i18n.py` — error and notification strings | language → English → key |
| Portal | `src/lib/messages.ts` + `LocaleProvider` | language → English → key |
| Mobile | `lib/src/l10n.dart` | language → English → key |

No framework was added. react-intl, next-intl, lingui and `flutter_localizations` codegen all solve problems these clients do not have — locale-routed URLs, ICU compilation, plural rule engines, `.arb` toolchains — and each would add a build step to render a few hundred short strings.

Catalogs are keyed by **language** (`hi`), not locale (`hi-IN`): "Hindi as spoken in India" and "Hindi" are the same words, and the region carries the money and the calendar, which live on the organization. Splitting per region would double the translation work to say the same sentences.

**Strings are fetched by key.** There is no `if (country === "India")` anywhere in either client. Navigation holds keys, not sentences. Adding Arabic is a new catalog and a registry entry — `LANGUAGES` already carries `rtl` for it, because a right-to-left interface is a layout decision rather than a translation one.

The language in force is the person's own, read from their account. Never `Accept-Language` or `navigator.language`: a shared machine in a dairy office would otherwise flip a supervisor's screen because of what the last person's laptop was set to. The header remains the fallback for requests that never authenticate.

## 7. What a client is told

`GET /v1/auth/me` carries the organization's locale context — currency, symbol, timezone, default language, the language list. Every client renders from that and holds no country configuration of its own; a second copy would be a second answer that disagrees the first time somebody changes a setting. It is also what makes localization available offline on the mobile app, which already caches the session.

`GET /v1/locales/countries` serves the onboarding list, so the portal and the app propose the same countries without either holding a copy.

## 8. Related

- [MOBILE-EXPERIENCES](MOBILE-EXPERIENCES.md) — how the field app consumes this
- [NOTIFICATION-ENGINE](NOTIFICATION-ENGINE.md) — recipient language and its organization fallback

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-14 | Engineering | Established by DEMO-013. |
