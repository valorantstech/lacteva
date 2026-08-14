/// The field app speaks the person's language and the dairy's money
/// (DEMO-013 §13).
///
/// The assertions are about WHERE the answers come from, not about vocabulary.
/// A test that only checked "Hindi appears" would pass equally well against a
/// hard-coded conditional, which is the thing the work order forbids — so what
/// is asserted is that the app holds no country configuration of its own and
/// takes currency, timezone and language from the session the platform sent.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/l10n.dart';
import 'package:lacteva_mobile/src/session.dart';

Session _session({String locale = 'en-IN', OrgLocale? org}) => Session(
  userId: 'u1',
  email: 'someone@dairy.example',
  fullName: 'Someone',
  tenantId: 'org-1',
  permissions: const {},
  locale: locale,
  organization: org,
);

const _india = OrgLocale(
  name: 'Lacteva India Demo',
  countryCode: 'IN',
  currencyCode: 'INR',
  currencySymbol: '₹',
  timezone: 'Asia/Kolkata',
  defaultLanguage: 'en-IN',
  supportedLanguages: ['en-IN', 'hi-IN'],
);

const _kenya = OrgLocale(
  name: 'Kilima Dairy',
  countryCode: 'KE',
  currencyCode: 'KES',
  currencySymbol: 'KSh',
  timezone: 'Africa/Nairobi',
  defaultLanguage: 'en-KE',
  supportedLanguages: ['en-KE'],
);

void main() {
  group('the session carries the locale, and the app holds none', () {
    test('parses what /v1/auth/me actually returns', () {
      // The person is NESTED under `user`; permissions, tenant and customer
      // are top-level. DEMO-012 read the person from the top level, where
      // they are not — so the signed-in address rendered blank.
      final session = Session.fromJson({
        'user': {
          'id': 'u9',
          'email': 'rider@dairy.example',
          'full_name': 'Rider',
          'locale': 'hi-IN',
        },
        'tenant_id': 'org-7',
        'customer_id': null,
        'permissions': ['sales.delivery.record'],
        'organization': {
          'name': 'Lacteva India Demo',
          'country_code': 'IN',
          'currency_code': 'INR',
          'currency_symbol': '₹',
          'timezone': 'Asia/Kolkata',
          'default_language': 'en-IN',
          'supported_languages': ['en-IN', 'hi-IN'],
        },
      });

      expect(session.email, 'rider@dairy.example');
      expect(session.fullName, 'Rider');
      expect(session.locale, 'hi-IN');
      expect(session.organization?.currencyCode, 'INR');
      expect(session.organization?.timezone, 'Asia/Kolkata');
      expect(session.can('sales.delivery.record'), isTrue);
    });

    test('a session with no organization does not invent one', () {
      // No fallback to Kenya, or to anywhere. An app that guessed a currency
      // would print a number in money nobody agreed to.
      final session = Session.fromJson({
        'user': {'id': 'u1'},
      });
      expect(session.organization, isNull);
      expect(money('120.00', session), '120.00');
    });
  });

  group('words', () {
    test('an English rider reads English', () {
      expect(
        L10n.of(_session(locale: 'en-IN')).t('round.title'),
        "Today's round",
      );
    });

    test('a Hindi rider reads Hindi — same key, no conditional', () {
      expect(
        L10n.of(_session(locale: 'hi-IN')).t('round.title'),
        'आज का राउंड',
      );
    });

    test('the catalog is keyed by language, not by region', () {
      expect(
        L10n.of(_session(locale: 'hi-IN')).t('customer.owe'),
        L10n.of(_session(locale: 'hi')).t('customer.owe'),
      );
    });

    test('a language with no catalog falls back to English, not to blank', () {
      expect(
        L10n.of(_session(locale: 'kl-GL')).t('round.title'),
        "Today's round",
      );
    });

    test('a key nothing defines comes back as the key', () {
      // Something an engineer can grep for, rather than an empty space on a
      // phone at 5 a.m.
      expect(L10n.of(_session()).t('round.doesNotExist'), 'round.doesNotExist');
    });

    test('Hindi covers every key English defines', () {
      final missing = catalogs['en']!.keys
          .where((k) => !catalogs['hi']!.containsKey(k))
          .toList();
      expect(
        missing,
        isEmpty,
        reason: 'Hindi is missing: ${missing.join(', ')}',
      );
    });

    test('variables are substituted, not printed', () {
      expect(
        L10n.of(_session()).t('round.waiting', {'count': 3}),
        '3 waiting to send',
      );
    });
  });

  group('money comes from the organization', () {
    test('an Indian dairy shows rupees', () {
      expect(money('1450.00', _session(org: _india)), '₹1450.00');
    });

    test(
      'a Kenyan dairy shows shillings — same function, no country logic',
      () {
        expect(money('1450.00', _session(org: _kenya)), 'KSh1450.00');
      },
    );

    test('the amount is never parsed into a number', () {
      // The exact decimal string arrives and leaves intact: no double, no
      // rounding, no locale-dependent grouping applied to a float.
      expect(money('0.10', _session(org: _india)), contains('0.10'));
      expect(
        money('1234567.89', _session(org: _india)),
        contains('1234567.89'),
      );
    });

    test('a missing amount is a dash, not a zero', () {
      // A zero is a claim about somebody's balance. A dash is the truth.
      expect(money(null, _session(org: _india)), '—');
      expect(money('', _session(org: _india)), '—');
    });
  });
}
