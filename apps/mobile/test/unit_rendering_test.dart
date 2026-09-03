/// No screen renders a unit it did not read (D-21 / WO-70).
///
/// The handset said "L" on the home screen over a total the platform had
/// weighed, and "kg" on every other screen whatever the dairy traded in —
/// thirty-three literals, and a formatter whose default unit was a guess. The
/// unit now comes with the record (`weight_unit`, `quantity_unit`) or, for
/// the label on a field the operator is about to fill, from the dairy's own
/// setting on the session. The last test greps `lib/` for the literal so the
/// guess cannot come back.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/collection_wizard.dart';
import 'package:lacteva_mobile/src/format.dart';
import 'package:lacteva_mobile/src/session.dart';

class _Fake extends ApiClient {
  final steps = <(String, Map<String, dynamic>)>[];

  @override
  Future<Map<String, dynamic>> txStep(String path, {Object? body}) async {
    steps.add((path, (body as Map?)?.cast<String, dynamic>() ?? const {}));
    return {
      'id': 't1',
      'state': path.endsWith('/weight') ? 'QUALITY_PENDING' : 'PRICED',
      'net_weight': 10,
      'weight_unit': 'litre',
      'trade_unit': 'kg',
      'trade_quantity': 10.3,
      'conversion_factor': '1.0300',
      'fat': 4.1,
      'snf': 8.5,
      'clr': 27,
      'pricing_status': 'priced',
      'pricing_detail': 'RC-2026-MAIN v1',
      'unit_price': '45.00',
      'gross_amount': '463.50',
      'currency': 'INR',
      'rejected_reason': null,
    };
  }
}

Session _session(String unit, String label) => Session(
  userId: 'u1',
  email: 'op@x.example',
  fullName: 'Operator',
  tenantId: 'org-1',
  permissions: const {'collection.session.manage'},
  organization: OrgLocale(
    name: 'Lacteva India Demo',
    countryCode: 'IN',
    currencyCode: 'INR',
    currencySymbol: '₹',
    timezone: 'Asia/Kolkata',
    defaultLanguage: 'en',
    supportedLanguages: const ['en'],
    quantityUnit: unit,
    quantityUnitLabel: label,
  ),
);

Future<void> _pump(WidgetTester tester, ApiClient client, Session session, {int step = 2}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: CollectionWizardScreen(
        client: client,
        sessionId: 's1',
        centerId: 'centre-1',
        session: session,
        initialStep: step,
        initialTransaction: const {'id': 't1', 'state': 'MILK_RECEIVED'},
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('the unit is the dairy\'s, read from the session', () {
    test('the symbol comes from the platform\'s word, and nothing is guessed', () {
      expect(unitLabel('litre'), 'L');
      expect(unitLabel('kg'), 'kg');
      expect(unitLabel('mixed'), 'mixed');
      expect(unitLabel(null), '');
      expect(orgUnit(_session('litre', 'L')), 'L');
      expect(orgUnit(_session('kg', 'kg')), 'kg');
      // A record's own unit wins over the dairy's; a record with none falls
      // back to the dairy's, never to a constant.
      expect(recordUnit('kg', _session('litre', 'L')), 'kg');
      expect(recordUnit(null, _session('litre', 'L')), 'L');
    });

    test('a session from the platform carries the unit it sent', () {
      final session = Session.fromJson({
        'user': {'id': 'u', 'email': 'e', 'full_name': 'n'},
        'tenant_id': 'org',
        'permissions': [],
        'organization': {
          'name': 'Dairy',
          'country_code': 'IN',
          'currency_code': 'INR',
          'currency_symbol': '₹',
          'timezone': 'Asia/Kolkata',
          'quantity_unit': 'litre',
          'quantity_unit_label': 'L',
          'trade_unit': 'kg',
          'trade_unit_label': 'kg',
          'conversion_factor': '1.0300',
        },
      });
      expect(session.organization?.quantityUnit, 'litre');
      expect(session.organization?.quantityUnitLabel, 'L');
      expect(session.organization?.tradeUnitLabel, 'kg');
      expect(session.organization?.conversionFactor, '1.0300');
      // Round-trips through the cache the app keeps for offline use.
      expect(OrgLocale.fromJson(session.organization!.toJson()).quantityUnitLabel, 'L');
    });

    testWidgets('a litre dairy\'s weight step is labelled in litres', (tester) async {
      await _pump(tester, _Fake(), _session('litre', 'L'));
      expect(find.widgetWithText(TextField, 'Gross (L)'), findsOneWidget);
      expect(find.widgetWithText(TextField, 'Tare (L)'), findsOneWidget);
      expect(find.textContaining('kg'), findsNothing);
    });

    testWidgets('a kilogram dairy\'s weight step is labelled in kilograms', (tester) async {
      await _pump(tester, _Fake(), _session('kg', 'kg'));
      expect(find.widgetWithText(TextField, 'Gross (kg)'), findsOneWidget);
      expect(find.widgetWithText(TextField, 'Tare (kg)'), findsOneWidget);
      expect(find.textContaining(' L'), findsNothing);
    });

    testWidgets('the ceiling message speaks the dairy\'s unit, and no unit is sent', (
      tester,
    ) async {
      final client = _Fake();
      await _pump(tester, client, _session('litre', 'L'));
      await tester.enterText(find.widgetWithText(TextField, 'Gross (L)'), '1200');
      await tester.enterText(find.widgetWithText(TextField, 'Tare (L)'), '2');
      await tester.tap(find.text('Capture weight'));
      await tester.pumpAndSettle();
      expect(find.text('gross exceeds 200 L limit'), findsOneWidget);
      expect(client.steps, isEmpty);

      await tester.enterText(find.widgetWithText(TextField, 'Gross (L)'), '12');
      await tester.tap(find.text('Capture weight'));
      await tester.pumpAndSettle();
      final weight = client.steps.single;
      expect(weight.$1, endsWith('/weight'));
      // D-21: the platform applies the ORGANISATION'S unit and would refuse
      // any other; the handset has no business asserting one.
      expect(weight.$2.containsKey('unit'), isFalse);
    });

    testWidgets('the review shows the measured figure, the paid figure and the factor', (
      tester,
    ) async {
      final client = _Fake();
      await _pump(tester, client, _session('litre', 'L'), step: 3);
      await tester.enterText(find.widgetWithText(TextField, 'FAT %'), '4.1');
      await tester.enterText(find.widgetWithText(TextField, 'SNF %'), '8.5');
      await tester.enterText(find.widgetWithText(TextField, 'CLR'), '27');
      await tester.tap(find.text('Capture quality'));
      await tester.pumpAndSettle();
      // The unit READ from the record, not the session: the record says litres
      // were measured and kilograms are paid at 1.0300, both figures shown.
      expect(find.text('Net weight: 10 L'), findsOneWidget);
      expect(find.text('Paid quantity: 10.3 kg (x 1.0300 kg/L)'), findsOneWidget);
      expect(find.textContaining('45.00 INR/kg'), findsOneWidget);
    });
  });

  test('no screen in lib/ writes kg next to a number it did not read', () {
    // The grep that measured the defect, kept as a guard. `format.dart` and
    // `session.dart` document the pre-WO-70 fallback; `l10n.dart` catalogs
    // carry `{unit}` placeholders and the literal `kg/L` of a declared factor;
    // `build_flags`/comments are not screens.
    // `api.dart` carries the same documented fallback on the two report views
    // (a platform from before the field existed measured in kilograms).
    final allowed = {
      'lib/src/format.dart',
      'lib/src/session.dart',
      'lib/src/l10n.dart',
      'lib/src/api.dart',
    };
    final offenders = <String>[];
    for (final file in Directory('lib').listSync(recursive: true).whereType<File>()) {
      if (!file.path.endsWith('.dart') || allowed.contains(file.path)) continue;
      final lines = file.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        final code = lines[i].split('//').first;
        if (RegExp(r'''['"] ?kg['"]|\} kg\b|/kg\b''').hasMatch(code)) {
          offenders.add('${file.path}:${i + 1}: ${lines[i].trim()}');
        }
      }
    }
    expect(offenders, isEmpty);
  });
}
