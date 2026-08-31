// The owner's hand on the rate, at the counter (WO-51b; BR-0029).
//
// D-15 asked for a rate the owner may explicitly edit. D-3 says never silent,
// always attributed. The tests that matter are the ones about who is offered
// the control at all, and about the screen refusing to pretend when it cannot
// deliver — not the happy path.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/collection_wizard.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';
import 'package:lacteva_mobile/src/session.dart';

Session _sessionWith(List<String> permissions) => Session.fromJson({
  'id': 'u1',
  'email': 'someone@dairy.example',
  'full_name': 'Someone',
  'tenant_id': 'org-1',
  'customer_id': null,
  'locale': 'en',
  'permissions': permissions,
});

const _priced = {
  'id': 'tx-1',
  'state': 'PRICED',
  'net_weight': 25.0,
  'fat': 4.2,
  'snf': 8.45,
  'clr': 27.5,
  'pricing_status': 'priced',
  'unit_price': '45.0000',
  'gross_amount': '1125.00',
  'currency': 'INR',
  'pricing_detail': 'MVP-CARD v1 band [4.0, 5.0)',
};

class _Fake extends ApiClient {
  _Fake({Map<String, dynamic>? tx}) : _tx = tx ?? Map.of(_priced);
  final Map<String, dynamic> _tx;
  final List<({String path, Object? body})> calls = [];

  @override
  Future<Map<String, dynamic>> txStep(String path, {Object? body}) async {
    calls.add((path: path, body: body));
    return _tx;
  }

  @override
  Future<Map<String, dynamic>> getMilkTransaction(String id) async => _tx;
}

/// An offline client that has already concluded it cannot reach the platform.
OfflineApiClient _offlineClient() => OfflineApiClient(
  queue: SyncQueue(MemoryOfflineStore()),
  deviceId: 'test-device',
  forceOffline: true,
);

Future<void> _pumpReview(
  WidgetTester tester, {
  required List<String> permissions,
  ApiClient? client,
  Map<String, dynamic>? tx,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: CollectionWizardScreen(
        client: client ?? _Fake(tx: tx),
        sessionId: 's1',
        session: _sessionWith(permissions),
        initialStep: 4, // the review step, where the rate is shown
        initialTransaction: tx ?? Map.of(_priced),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a holder is offered the control', (tester) async {
    await _pumpReview(tester, permissions: ['pricing.rate.override']);
    expect(find.text('Edit rate'), findsOneWidget);
  });

  testWidgets('the operator is not offered it AT ALL — absent, not disabled', (tester) async {
    // A greyed-out button still tells the person at the counter that the
    // capability exists and they are not trusted with it. That is a different
    // and worse message than a screen that simply does not offer it.
    await _pumpReview(tester, permissions: ['collection.transaction.record']);
    expect(find.text('Edit rate'), findsNothing);
    expect(
      find.byWidgetPredicate((w) => w is TextButton && w.onPressed == null),
      findsNothing,
      reason: 'the control must be absent, not present and disabled',
    );
  });

  testWidgets('the dialog shows what the rate is being changed FROM', (tester) async {
    await _pumpReview(tester, permissions: ['pricing.rate.override']);
    await tester.tap(find.text('Edit rate'));
    await tester.pumpAndSettle();

    // Whoever changes a farmer's rate should see the number they are changing.
    expect(find.textContaining('Card rate: 45.0000'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Reason (required)'), findsOneWidget);
  });

  testWidgets('an empty reason is refused before any round trip', (tester) async {
    final client = _Fake();
    await _pumpReview(tester, permissions: ['pricing.rate.override'], client: client);
    await tester.tap(find.text('Edit rate'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Change rate'));
    await tester.pumpAndSettle();

    expect(find.text('A reason is required'), findsOneWidget);
    expect(client.calls, isEmpty, reason: 'nothing should have been sent');
  });

  testWidgets('a rate of zero is refused', (tester) async {
    final client = _Fake();
    await _pumpReview(tester, permissions: ['pricing.rate.override'], client: client);
    await tester.tap(find.text('Edit rate'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'New rate (INR/kg)'), '0');
    await tester.tap(find.text('Change rate'));
    await tester.pumpAndSettle();

    expect(find.text('Enter a rate greater than zero'), findsOneWidget);
    expect(client.calls, isEmpty);
  });

  testWidgets('offline, the screen says why instead of pretending', (tester) async {
    // OFF-001 carries no kind for an override, deliberately: the rate is
    // resolved by the platform at quality capture, so a queued collection has
    // no rate to override, and a queue entry that decided a price on the
    // handset would put pricing in the client.
    await _pumpReview(
      tester,
      permissions: ['pricing.rate.override'],
      client: _offlineClient(),
    );
    await tester.tap(find.text('Edit rate'));
    await tester.pumpAndSettle();

    expect(find.textContaining('needs a connection'), findsOneWidget);
    // …and offers no way to submit something that cannot be submitted.
    expect(find.text('Change rate'), findsNothing);
  });

  testWidgets('an existing override shows both rates and the reason', (tester) async {
    final overridden = Map<String, dynamic>.of(_priced)
      ..['unit_price'] = '52.5000'
      ..['base_unit_price'] = '45.0000'
      ..['override_reason'] = 'quality re-tested at the counter';
    await _pumpReview(tester, permissions: ['pricing.rate.override'], tx: overridden);

    expect(find.textContaining('52.5000'), findsWidgets);
    expect(find.textContaining('Card rate 45.0000'), findsOneWidget);
    expect(find.textContaining('quality re-tested at the counter'), findsOneWidget);
  });
}
