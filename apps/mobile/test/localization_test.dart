/// The field app speaks the person's language and the dairy's money
/// (DEMO-013 §13).
///
/// The assertions are about WHERE the answers come from, not about vocabulary.
/// A test that only checked "Hindi appears" would pass equally well against a
/// hard-coded conditional, which is the thing the work order forbids — so what
/// is asserted is that the app holds no country configuration of its own and
/// takes currency, timezone and language from the session the platform sent.
library;

import 'package:flutter/widgets.dart';
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

  group('the session resolves the real /v1/auth/me (DEMO-013 §4)', () {
    /// The payload below is the SHAPE THE PLATFORM ACTUALLY RETURNS, captured
    /// from a live `GET /v1/auth/me` rather than written from memory. That is
    /// the whole point of this test: DEMO-012's parser was written from
    /// memory, read `id`/`email`/`full_name` from the top level where they
    /// are not, and rendered a blank address for two milestones.
    Map<String, dynamic> realPayload() => {
      'user': {
        'id': '11111111-1111-1111-1111-111111111111',
        'tenant_id': '94340405-0918-4f8b-939c-a9205a9ead4b',
        'email': 'priya@lacteva-india.example.com',
        'full_name': 'Priya Raghavan',
        'locale': 'hi-IN',
        'is_active': true,
        'last_login_at': '2026-08-14T05:42:49.835392Z',
        'created_at': '2026-08-01T00:00:00Z',
      },
      'tenant_id': '94340405-0918-4f8b-939c-a9205a9ead4b',
      'organization': {
        'id': '94340405-0918-4f8b-939c-a9205a9ead4b',
        'name': 'Lacteva India Demo',
        'slug': 'lacteva-india-demo',
        'country_code': 'IN',
        'currency_code': 'INR',
        'currency_symbol': '₹',
        'timezone': 'Asia/Kolkata',
        'default_language': 'en-IN',
        'supported_languages': ['en-IN', 'hi-IN'],
        'languages': [
          {
            'tag': 'en-IN',
            'name': 'English',
            'endonym': 'English',
            'rtl': false,
          },
          {'tag': 'hi-IN', 'name': 'Hindi', 'endonym': 'हिन्दी', 'rtl': false},
        ],
      },
      'membership': {
        'status': 'active',
        'joined_at': '2026-08-14T05:42:49.835392Z',
      },
      'roles': [
        {
          'name': 'tenant-admin',
          'description': 'System role tenant-admin',
          'center_id': null,
        },
      ],
      'center_scope': null,
      'permissions': ['sales.delivery.record', 'organization.read'],
      'customer_id': null,
    };

    test('identifies the authenticated user', () {
      final s = Session.fromJson(realPayload());
      expect(s.userId, '11111111-1111-1111-1111-111111111111');
      expect(s.email, 'priya@lacteva-india.example.com');
      expect(s.fullName, 'Priya Raghavan');
      expect(s.locale, 'hi-IN');
    });

    test('identifies the organization and its locale context', () {
      final s = Session.fromJson(realPayload());
      expect(s.tenantId, '94340405-0918-4f8b-939c-a9205a9ead4b');
      expect(s.organizationId, s.tenantId);
      expect(s.organization?.name, 'Lacteva India Demo');
      expect(s.organization?.currencyCode, 'INR');
      expect(s.organization?.timezone, 'Asia/Kolkata');
    });

    test('identifies membership and effective permissions', () {
      final s = Session.fromJson(realPayload());
      expect(s.membershipStatus, 'active');
      expect(s.can('sales.delivery.record'), isTrue);
      expect(s.can('sales.invoice.issue'), isFalse);
    });

    test('carries role names but never decides with them', () {
      // DEMO-008 made roles editable rows. The role is readable for a support
      // call; the EXPERIENCE comes from capabilities, so a principal with the
      // permission and no recognisable role name still gets the round.
      final s = Session.fromJson(realPayload());
      expect(s.roleNames, contains('tenant-admin'));

      final renamed = realPayload()
        ..['roles'] = [
          {'name': 'Milk Round Supervisor (Bengaluru)', 'center_id': null},
        ];
      expect(experienceFor(Session.fromJson(renamed)), Experience.delivery);
    });

    test('a null centre scope is the whole organization', () {
      final s = Session.fromJson(realPayload());
      expect(s.centerScope, isNull);
      expect(s.coversCenter('any-centre-at-all'), isTrue);
    });

    test('a centre-scoped operator is confined to their centres', () {
      // Null and empty are different: null is everywhere, a list is exactly
      // those centres.
      final scoped = realPayload()..['center_scope'] = ['centre-a', 'centre-b'];
      final s = Session.fromJson(scoped);
      expect(s.coversCenter('centre-a'), isTrue);
      expect(s.coversCenter('centre-z'), isFalse);
    });

    test('a customer-scoped login is recognised as one', () {
      final household = realPayload()
        ..['customer_id'] = 'cus-42'
        ..['permissions'] = ['sales.invoice.read'];
      final s = Session.fromJson(household);
      expect(s.isCustomer, isTrue);
      expect(s.customerId, 'cus-42');
      expect(experienceFor(s), Experience.customer);
    });
  });

  group('Arabic and right-to-left (DEMO-014)', () {
    test('an Arabic rider reads Arabic', () {
      expect(L10n.of(_session(locale: 'ar-SA')).t('round.title'), 'جولة اليوم');
      expect(L10n.of(_session(locale: 'ar-AE')).t('customer.owe'), 'ما عليّ');
    });

    test('Arabic covers every key English defines', () {
      final missing = catalogs['en']!.keys
          .where((k) => !catalogs['ar']!.containsKey(k))
          .toList();
      expect(
        missing,
        isEmpty,
        reason: 'Arabic is missing: ${missing.join(', ')}',
      );
    });

    test('no catalog defines a key English does not', () {
      for (final language in ['hi', 'ar']) {
        final orphans = catalogs[language]!.keys
            .where((k) => !catalogs['en']!.containsKey(k))
            .toList();
        expect(orphans, isEmpty, reason: '$language has orphans: $orphans');
      }
    });

    test('Arabic is right to left and the others are not', () {
      expect(isRtl('ar-SA'), isTrue);
      expect(isRtl('ar'), isTrue);
      expect(isRtl('hi-IN'), isFalse);
      expect(isRtl('en-KE'), isFalse);
      expect(isRtl(null), isFalse);
    });

    test('the direction comes from the session, not from a screen', () {
      expect(directionFor(_session(locale: 'ar-SA')), TextDirection.rtl);
      expect(directionFor(_session(locale: 'en-IN')), TextDirection.ltr);
      expect(directionFor(null), TextDirection.ltr);
    });

    test('an Arabic variable substitutes like any other', () {
      expect(
        L10n.of(_session(locale: 'ar-SA')).t('round.waiting', {'count': 3}),
        contains('3'),
      );
    });
  });

  group('the app performs no timezone arithmetic (DEMO-014 §9)', () {
    test('a business date is rendered exactly as the platform sent it', () {
      // A handset cannot convert to an IANA zone without shipping tzdata, and
      // its own clock is not the dairy's. The platform computes the date; the
      // app shows it.
      expect(businessDate('2026-08-14'), '2026-08-14');
      expect(businessDate(null), '');
    });

    test('the organization clock is readable but never computed with', () {
      final session = _session(org: _india);
      expect(businessClock(session), 'Asia/Kolkata');
      expect(businessClock(null), 'UTC');
    });
  });
}
