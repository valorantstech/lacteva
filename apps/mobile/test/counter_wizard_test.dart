/// The counter transaction, hardened (P1-MOBILE-COUNTER-001).
///
/// What is pinned:
///   1. OFFLINE INPUT BOUNDS (audit D-8): the wizard refuses, before anything
///      can queue, exactly what the platform would refuse — the bounds are
///      the platform's own (`milk_collection/service.py`), not invented. A
///      mistyped 1200 kg must fail at the counter, not hours later at sync.
///   2. REJECTION ASKS WHY (audit D-7): the reason prints on the farmer's
///      official parchi; the hardcoded placeholder is gone, an empty reason
///      is refused, and the operator's own words travel to the platform.
///   3. THE PARCHI ON COMPLETION: an online completion fetches the platform's
///      slip (number + shareable text) and offers copy; a transport failure
///      leaves an explicit retry; an OFFLINE completion says "saved on this
///      phone — queued" and never pretends a slip number exists, because the
///      platform mints those.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/collection_wizard.dart';

class _Fake extends ApiClient {
  _Fake({this.offlineCompletion = false, this.slipFailsFirst = false});

  final bool offlineCompletion;
  bool slipFailsFirst;

  final List<(String, Map<String, dynamic>)> steps = [];
  int slipFetches = 0;
  String? lastRejectReason;

  Map<String, dynamic> _tx(Map<String, dynamic> over) => {
    'id': 't1',
    'state': 'NEW',
    'net_weight': 10,
    'fat': 4.1,
    'snf': 8.5,
    'clr': 27,
    'pricing_status': 'priced',
    'pricing_detail': 'RC-2026-MAIN v1',
    'unit_price': '45.00',
    'gross_amount': '450.00',
    'currency': 'INR',
    'rejected_reason': null,
    ...over,
  };

  @override
  Future<Map<String, dynamic>> txStep(String path, {Object? body}) async {
    final payload = (body as Map?)?.cast<String, dynamic>() ?? const {};
    steps.add((path, payload));
    if (path.endsWith('/reject')) {
      lastRejectReason = payload['reason']?.toString();
      return _tx({'state': 'REJECTED', 'rejected_reason': lastRejectReason});
    }
    if (path.endsWith('/complete')) {
      return _tx({
        'state': 'COMPLETED',
        'rejected_reason': lastRejectReason,
        if (offlineCompletion) 'offline': true,
        if (offlineCompletion) 'pricing_status': 'pending_sync',
      });
    }
    if (path.endsWith('/identify')) return _tx({'state': 'SUPPLIER_IDENTIFIED'});
    if (path.endsWith('/milk')) return _tx({'state': 'MILK_RECEIVED'});
    if (path.endsWith('/weight')) return _tx({'state': 'QUALITY_PENDING'});
    if (path.endsWith('/quality')) return _tx({'state': 'PRICED'});
    if (path.endsWith('/accept')) return _tx({'state': 'ACCEPTED'});
    return _tx({});
  }

  @override
  Future<Map<String, dynamic>> transactionSlip(String txId) async {
    slipFetches++;
    if (slipFailsFirst) {
      slipFailsFirst = false;
      throw const SocketException('no route to host');
    }
    return {
      'slip_number': 'SLP-2026-000042',
      'transaction_id': txId,
      'text': 'Anand Dairy\nSlip: SLP-2026-000042\nNet: 10 kg',
    };
  }
}

Future<void> _pump(WidgetTester tester, _Fake client, {int step = 0}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: CollectionWizardScreen(
        client: client,
        sessionId: 's1',
        initialStep: step,
      ),
    ),
  );
  await tester.pump();
}

/// Drive from the review step (4) by walking the real step calls first.
Future<void> _driveToReview(WidgetTester tester, _Fake client) async {
  await _pump(tester, client);
  await tester.enterText(find.byType(TextField).first, 'SUP-001');
  await tester.tap(find.text('Identify supplier'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Receive milk'));
  await tester.pumpAndSettle();
  await tester.enterText(find.widgetWithText(TextField, 'Gross (kg)'), '12');
  await tester.enterText(find.widgetWithText(TextField, 'Tare (kg)'), '2');
  await tester.tap(find.text('Capture weight'));
  await tester.pumpAndSettle();
  await tester.enterText(find.widgetWithText(TextField, 'FAT %'), '4.1');
  await tester.enterText(find.widgetWithText(TextField, 'SNF %'), '8.5');
  await tester.enterText(find.widgetWithText(TextField, 'CLR'), '27');
  await tester.tap(find.text('Capture quality'));
  await tester.pumpAndSettle();
  expect(find.text('Review'), findsOneWidget);
}

void main() {
  group('offline input bounds — the platform’s own rules, checked first', () {
    Future<_Fake> tryWeight(WidgetTester tester, String g, String t) async {
      final client = _Fake();
      await _pump(tester, client, step: 2);
      await tester.enterText(find.widgetWithText(TextField, 'Gross (kg)'), g);
      await tester.enterText(find.widgetWithText(TextField, 'Tare (kg)'), t);
      await tester.tap(find.text('Capture weight'));
      await tester.pumpAndSettle();
      return client;
    }

    testWidgets('malformed input never queues', (tester) async {
      final c = await tryWeight(tester, 'abc', '2');
      expect(find.text('Enter gross and tare as numbers'), findsOneWidget);
      expect(c.steps, isEmpty);
    });

    testWidgets('zero and negative are refused in the platform’s words', (
      tester,
    ) async {
      final c = await tryWeight(tester, '0', '0');
      expect(find.text('gross must be > 0 and tare >= 0'), findsOneWidget);
      expect(c.steps, isEmpty);
      final c2 = await tryWeight(tester, '12', '-1');
      expect(c2.steps, isEmpty);
    });

    testWidgets('the 200 kg ceiling holds; the boundary itself passes', (
      tester,
    ) async {
      final over = await tryWeight(tester, '200.5', '2');
      expect(
        find.text('gross weight exceeds 200.0 kg limit'),
        findsOneWidget,
      );
      expect(over.steps, isEmpty);

      final atLimit = await tryWeight(tester, '200.0', '2');
      expect(atLimit.steps, hasLength(1), reason: 'the boundary is legal');
    });

    testWidgets('tare must stay below gross', (tester) async {
      final c = await tryWeight(tester, '10', '10');
      expect(find.text('tare must be less than gross'), findsOneWidget);
      expect(c.steps, isEmpty);
    });

    testWidgets('quality outside QUALITY_RANGES never queues', (tester) async {
      final client = _Fake();
      await _pump(tester, client, step: 3);
      await tester.enterText(find.widgetWithText(TextField, 'FAT %'), '15.1');
      await tester.enterText(find.widgetWithText(TextField, 'SNF %'), '8.5');
      await tester.enterText(find.widgetWithText(TextField, 'CLR'), '27');
      await tester.tap(find.text('Capture quality'));
      await tester.pumpAndSettle();
      expect(find.text('fat out of range [0.0, 15.0]'), findsOneWidget);
      expect(client.steps, isEmpty);

      // The inclusive boundary is legal — exactly as on the platform.
      await tester.enterText(find.widgetWithText(TextField, 'FAT %'), '15.0');
      await tester.enterText(find.widgetWithText(TextField, 'CLR'), '20.0');
      await tester.tap(find.text('Capture quality'));
      await tester.pumpAndSettle();
      expect(client.steps, hasLength(1));
    });
  });

  group('rejection asks why', () {
    testWidgets('an empty reason is refused; the operator’s words travel', (
      tester,
    ) async {
      final client = _Fake();
      await _driveToReview(tester, client);

      await tester.tap(find.text('Reject…'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Reject & complete'));
      await tester.pumpAndSettle();
      expect(
        find.text('Say why the milk is rejected — it prints on the parchi'),
        findsOneWidget,
      );
      expect(client.lastRejectReason, isNull);

      await tester.enterText(
        find.widgetWithText(TextField, 'Rejection reason'),
        'Sour smell at the can',
      );
      await tester.tap(find.text('Reject & complete'));
      await tester.pumpAndSettle();
      expect(client.lastRejectReason, 'Sour smell at the can');
      expect(find.text('Rejected: Sour smell at the can'), findsOneWidget);
    });
  });

  group('the parchi on completion', () {
    testWidgets('an online completion shows the platform’s slip and copy', (
      tester,
    ) async {
      final client = _Fake();
      await _driveToReview(tester, client);
      await tester.tap(find.text('Accept & complete'));
      await tester.pumpAndSettle();

      expect(find.text('Transaction COMPLETED'), findsOneWidget);
      expect(find.text('Parchi SLP-2026-000042'), findsOneWidget);
      expect(find.textContaining('Slip: SLP-2026-000042'), findsOneWidget);
      expect(find.text('Copy parchi text'), findsOneWidget);
      expect(client.slipFetches, 1);
    });

    testWidgets('a slip transport failure leaves an explicit retry', (
      tester,
    ) async {
      final client = _Fake(slipFailsFirst: true);
      await _driveToReview(tester, client);
      await tester.tap(find.text('Accept & complete'));
      await tester.pumpAndSettle();

      expect(find.text('Get parchi'), findsOneWidget);
      await tester.tap(find.text('Get parchi'));
      await tester.pumpAndSettle();
      expect(find.text('Parchi SLP-2026-000042'), findsOneWidget);
      expect(client.slipFetches, 2);
    });

    testWidgets('an offline completion is honest: queued, no invented slip', (
      tester,
    ) async {
      final client = _Fake(offlineCompletion: true);
      await _driveToReview(tester, client);
      await tester.tap(find.text('Accept & complete'));
      await tester.pumpAndSettle();

      expect(
        find.text('Saved on this phone — queued to sync'),
        findsOneWidget,
      );
      expect(find.textContaining('issued when this phone syncs'), findsOneWidget);
      expect(client.slipFetches, 0, reason: 'no slip exists to fetch yet');
      expect(find.textContaining('SLP-'), findsNothing);
    });
  });
}
