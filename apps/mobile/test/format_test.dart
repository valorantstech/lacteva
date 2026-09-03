/// Numbers wear their units (WO-64).
///
/// The on-glass review found "214.000 L" in the round header — three decimals
/// no dairy says out loud — and "0.00" as a day's value with no currency
/// beside it. The second is WO-61's defect in a smaller font: a number without
/// its denomination is not money, on any screen.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/format.dart';
import 'package:lacteva_mobile/src/session.dart';

Session _session({String symbol = '₹', String code = 'INR'}) => Session(
  userId: 'u1',
  email: 'a@b.example',
  fullName: 'A',
  tenantId: 'org-1',
  permissions: const {},
  organization: OrgLocale(
    name: 'Sitara Dairy',
    countryCode: 'IN',
    currencyCode: code,
    currencySymbol: symbol,
    timezone: 'Asia/Kolkata',
    defaultLanguage: 'en',
    supportedLanguages: const ['en'],
  ),
);

void main() {
  group('a quantity is said the way a dairy says it', () {
    test('three stored decimals become the one a person reads', () {
      expect(quantity('214.000', unit: 'L'), '214.0 L');
      expect(quantity(214.0, unit: 'L'), '214.0 L');
      expect(quantity('2.500', unit: 'L'), '2.5 L');
    });

    test('the unit is always there, and can be the one the platform sent', () {
      expect(quantity('50.000', unit: 'kg'), '50.0 kg');
    });

    test('nothing is invented from nothing', () {
      expect(quantity(null, unit: 'L'), '—');
      expect(quantity('', unit: 'L'), '—');
      expect(quantity('not a number', unit: 'L'), '—');
    });

    test('the number is never converted, only rendered', () {
      // Kilograms in, kilograms out. A density constant here would be the app
      // deciding a business fact.
      expect(quantity('100.000', unit: 'kg'), '100.0 kg');
    });
  });

  group('money carries its currency or says it cannot', () {
    test('the symbol comes from the organization, never from the app', () {
      expect(money('84.00', _session()), '₹84.00');
      expect(money('84.00', _session(symbol: '', code: 'KES')), '84.00 KES');
    });

    test('zero is still money and still needs its currency', () {
      // The exact string the review found: "0.00 value", undenominated.
      expect(money('0.00', _session()), '₹0.00');
      expect(money('0.00', _session()), isNot('0.00'));
    });

    test('with no organization it renders the amount and implies nothing', () {
      expect(money('84.00', null), '84.00');
    });

    test('absent money is a dash, not a zero', () {
      // A zero is a fact — "nothing was sold". A dash is the absence of one.
      expect(money(null, _session()), '—');
      expect(money('', _session()), '—');
    });
  });

  group('the other two', () {
    test('a percentage reads to one decimal', () {
      expect(percent('4.25'), '4.3%');
      expect(percent(null), '—');
    });

    test('a count is whole — a farmer is not 24.0', () {
      expect(count('24'), '24');
      expect(count(24.0), '24');
      expect(count(null), '—');
    });
  });
}
