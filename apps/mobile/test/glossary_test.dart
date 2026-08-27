/// One word per concept, made executable (LACTEVA-ADMIN-005; decision D-4).
///
/// The mirror of the portal's `glossary.test.ts`, and it exists for the same
/// reason: the terminology audit found this catalog saying "centre" in three
/// values and "center" in eight, with no rule anywhere deciding which. That is
/// how a product ends up with a third dialect — every new string copies
/// whichever of the two its author happened to read last.
///
/// EN values only. Hindi and Arabic spell neither word in Latin script, and
/// what a household calls an invoice in its own language is a translation
/// judgement rather than drift (the architect's ruling on A4).
///
/// Keys are never checked. `center.listTitle` and `wizard.supplierCode` are
/// addresses that callers hold; renaming them would break every call site to
/// no reader's benefit.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/l10n.dart';

/// Interpolation variables are a caller's contract, not prose: `{center}` in
/// `history.title` must survive a spelling rule aimed at English words.
String _visible(String value) => value.replaceAll(RegExp(r'\{[^}]*\}'), ' ');

/// The only survivors of "Bill" (ruling B2): "Billing" names the activity and
/// the section, never the document. There is deliberately no "billable" —
/// ruling B1 put state words under the document noun.
String _withoutAllowed(String value) => value
    .replaceAll(RegExp(r'\bBilling\b'), ' ')
    .replaceAll(RegExp(r'\bbilling period\b', caseSensitive: false), ' ');

List<String> _offenders(RegExp pattern, {bool allow = false}) {
  final en = catalogs['en']!;
  return en.entries
      .where((e) => !(allow && e.key.startsWith('billing.')))
      .where((e) {
        final text = allow ? _withoutAllowed(_visible(e.value)) : _visible(e.value);
        return pattern.hasMatch(text);
      })
      .map((e) => e.key)
      .toList()
    ..sort();
}

void main() {
  group('the D-4 glossary, in the EN catalog', () {
    test('spells it Centre, never Center', () {
      expect(
        _offenders(RegExp(r'\bcenters?\b', caseSensitive: false)),
        isEmpty,
        reason: 'en-IN: a dairy in Karnataka reads Centre on the sign',
      );
    });

    test('says Invoice, never Bill', () {
      expect(
        _offenders(
          RegExp(r'\bbills?\b|\bbilled\b|\bbillable\b', caseSensitive: false),
          allow: true,
        ),
        isEmpty,
      );
    });

    test('the capture wizard names the person a Farmer', () {
      // Ruling B3: the operator at the intake bay is looking at a farmer. The
      // business entity keeps the name Supplier wherever a contract or a
      // settlement is meant — which is why this asserts the wizard values
      // specifically rather than sweeping the whole catalog for "supplier".
      final en = catalogs['en']!;
      expect(en['wizard.identify'], 'Identify farmer');
      expect(en['wizard.supplier'], 'Farmer');
      expect(en['wizard.supplierCode'], 'Farmer code');
      expect(en['queue.kind.identify_supplier'], 'Identify farmer');
    });

    test('is actually reading a populated catalog', () {
      // Without this the assertions above pass beautifully against nothing.
      final en = catalogs['en']!;
      expect(en.length, greaterThan(200));
      expect(en['center.listTitle'], 'Collection centres');
      expect(en['customer.bill'], 'Invoice');
    });
  });
}
