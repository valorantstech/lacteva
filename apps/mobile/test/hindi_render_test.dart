/// The collection persona actually renders in Hindi (P1-LOCALE-I18N-001).
///
/// Before this milestone the whole collection stack was hardcoded English, so
/// a Hindi-speaking operator — the pilot's primary user — read English at every
/// step of their main job. The catalog now covers it, and this pins the whole
/// chain end to end: session locale → catalog → widget, on the pilot's real
/// geometry (320×568, the cheap Android the driver screen is already tested
/// on), with a RenderFlex overflow treated as a failure.
///
/// What this is NOT: physical-device visual proof. It proves encoding, lookup
/// and layout constraints under Flutter's test binding — a real handset pass
/// is a separate, honest claim (P0-PILOT-004's kind), not made here.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/collection_wizard.dart';
import 'package:lacteva_mobile/src/l10n.dart';
import 'package:lacteva_mobile/src/session.dart';
import 'package:lacteva_mobile/src/transactions_history.dart';

Session _session(String locale) => Session.fromJson({
  'id': 'u1',
  'email': 'operator@dairy.example',
  'full_name': 'ऑपरेटर',
  'tenant_id': 'org-1',
  'customer_id': null,
  'locale': locale,
  'permissions': ['collection.session.manage', 'collection.center.read'],
});

class _Fake extends ApiClient {
  @override
  Future<Map<String, dynamic>> listMilkTransactions({
    required String centerId,
    int limit = 20,
    int offset = 0,
  }) async => {'items': [], 'total': 0, 'limit': limit, 'offset': offset};
}

/// The pilot's real geometry: a 320px-wide phone, where a long Devanagari
/// string either fits or overflows visibly.
Future<void> _pumpSmall(WidgetTester tester, Widget child) async {
  tester.view.physicalSize = const Size(320, 568);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(home: child));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the capture wizard speaks Hindi at 320px', (tester) async {
    await _pumpSmall(
      tester,
      CollectionWizardScreen(
        client: _Fake(),
        sessionId: 's1',
        session: _session('hi-IN'),
        initialStep: 2, // the weight step: labels, button, units
      ),
    );

    final t = L10n('hi');
    // Devanagari on screen, not the English fallback.
    expect(find.text(t.t('wizard.weight')), findsOneWidget);
    expect(find.text(t.t('wizard.captureWeight')), findsOneWidget);
    expect(t.t('wizard.weight'), isNot('Weight'), reason: 'really translated');
    // Units and domain tokens stay Latin — a scale reads kg in any language.
    expect(find.text(t.t('wizard.grossKg')), findsOneWidget);
    expect(t.t('wizard.grossKg'), contains('kg'));
    // No RenderFlex overflow at 320px.
    expect(tester.takeException(), isNull);
  });

  testWidgets('the quality step keeps FAT/SNF/CLR Latin in Hindi', (
    tester,
  ) async {
    await _pumpSmall(
      tester,
      CollectionWizardScreen(
        client: _Fake(),
        sessionId: 's1',
        session: _session('hi-IN'),
        initialStep: 3,
      ),
    );
    final t = L10n('hi');
    expect(find.text(t.t('wizard.quality')), findsOneWidget);
    for (final key in ['wizard.fatLabel', 'wizard.snfLabel', 'wizard.clrLabel']) {
      final label = t.t(key);
      expect(find.text(label), findsOneWidget);
      // The instrument's vocabulary is international; the sentence around it
      // is not. Translating "FAT" would not help an operator reading a meter.
      expect(
        RegExp(r'FAT|SNF|CLR').hasMatch(label),
        isTrue,
        reason: '$key should keep its instrument token: $label',
      );
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('the history screen speaks Hindi and fits 320px', (tester) async {
    await _pumpSmall(
      tester,
      TransactionHistoryScreen(
        client: _Fake(),
        centerId: 'c1',
        centerName: 'ग्राम संग्रह केंद्र',
        session: _session('hi-IN'),
      ),
    );
    final t = L10n('hi');
    expect(find.text(t.t('history.empty')), findsOneWidget);
    expect(t.t('history.empty'), isNot(L10n('en').t('history.empty')));
    expect(tester.takeException(), isNull);
  });

  testWidgets('Arabic renders right-to-left without overflow', (tester) async {
    // Direction comes from the session (directionFor) and is applied at the
    // router; here the wrapper is explicit so the WIDGETS are what is tested.
    await _pumpSmall(
      tester,
      Directionality(
        textDirection: TextDirection.rtl,
        child: CollectionWizardScreen(
          client: _Fake(),
          sessionId: 's1',
          session: _session('ar'),
          initialStep: 2,
        ),
      ),
    );
    final t = L10n('ar');
    expect(find.text(t.t('wizard.captureWeight')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test('Hindi and Arabic values are real script, not English copies', () {
    // A catalog can pass parity while holding English in every slot. These
    // are the operator-critical keys; each must actually differ and carry the
    // script's own codepoints.
    const devanagari = r'[ऀ-ॿ]';
    const arabic = r'[؀-ۿ]';
    for (final key in [
      'wizard.weight',
      'wizard.quality',
      'wizard.review',
      'wizard.captureWeight',
      'history.empty',
      'center.listTitle',
      'common.couldNotReach',
    ]) {
      final en = L10n('en').t(key);
      final hi = L10n('hi').t(key);
      final ar = L10n('ar').t(key);
      expect(hi, isNot(en), reason: '$key is untranslated in Hindi');
      expect(ar, isNot(en), reason: '$key is untranslated in Arabic');
      expect(
        RegExp(devanagari).hasMatch(hi),
        isTrue,
        reason: '$key Hindi is not Devanagari: $hi',
      );
      expect(
        RegExp(arabic).hasMatch(ar),
        isTrue,
        reason: '$key Arabic is not Arabic script: $ar',
      );
    }
  });
}
