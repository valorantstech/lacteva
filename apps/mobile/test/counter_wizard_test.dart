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
  _Fake({
    this.offlineCompletion = false,
    this.slipFailsFirst = false,
    this.suppliers = const [
      {
        'id': 's-14',
        'code': 'SUP-014',
        'status': 'active',
        'full_name': 'Vasanthi Prabhu',
        'phone': '+91 98450 00016',
      },
    ],
    this.searchFails = false,
  });

  final bool offlineCompletion;
  bool slipFailsFirst;

  /// WO-64: what the farmer lookup finds, and what it was asked.
  final List<Map<String, dynamic>> suppliers;
  final bool searchFails;
  String? searchedQuery;
  String? searchedCentre;
  int searches = 0;

  @override
  Future<SupplierPageResult> listSuppliers({
    String query = '',
    String? centerId,
    int limit = 20,
    int offset = 0,
  }) async {
    searches++;
    searchedQuery = query;
    searchedCentre = centerId;
    if (searchFails) throw const SocketException('no route to host');
    return SupplierPageResult.fromJson(<String, dynamic>{
      'items': suppliers,
      'total': suppliers.length,
      'limit': limit,
      'offset': offset,
    });
  }

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
        // WO-64: the counter knows which centre it is standing in, which is
        // what narrows the farmer lookup.
        centerId: 'centre-1',
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
  await tester.tap(find.text('Identify farmer'));
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
  group('the animals the counter can take (WO-55)', () {
    testWidgets('sheep is on the list, and the code travels to the platform', (
      tester,
    ) async {
      // The vocabulary omitted the one common Indian dairy animal it had no
      // reason to omit. The label is translated; the VALUE sent stays the raw
      // code the platform stores.
      final client = _Fake();
      await _pump(tester, client, step: 1);

      await tester.tap(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();
      for (final animal in ['cow', 'buffalo', 'goat', 'sheep', 'mixed']) {
        expect(
          find.text(animal),
          findsWidgets,
          reason: '$animal must be offered at the counter',
        );
      }

      await tester.tap(find.text('sheep').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Receive milk'));
      await tester.pumpAndSettle();

      final milk = client.steps.singleWhere((s) => s.$1.endsWith('/milk'));
      expect(milk.$2['milk_type'], 'sheep');
    });
  });

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
        find.text('gross exceeds 200 kg limit'),
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

  group('finding a farmer whose code is not to hand (WO-64)', () {
    testWidgets('the code field keeps focus and stays the primary route', (
      tester,
    ) async {
      // The recovery path must not cost the common path a keystroke: an
      // operator who knows the code types it the moment the screen opens.
      final client = _Fake();
      await _pump(tester, client, step: 0);
      final code = tester.widget<TextField>(
        find.widgetWithText(TextField, 'Farmer code'),
      );
      expect(code.autofocus, isTrue);
    });

    testWidgets('choosing a result IDENTIFIES the farmer and advances', (
      tester,
    ) async {
      // WO-69. WO-64 had the choice only fill the code field, leaving the
      // operator to tap "Identify farmer" — two taps where one will do. The
      // result row already shows name, code and phone, so choosing it is the
      // confirmation; the wizard can step back if the wrong person was picked.
      final client = _Fake();
      await _pump(tester, client, step: 0);

      await tester.enterText(
        find.widgetWithText(TextField, 'Search by name or phone'),
        'Vasanthi',
      );
      await tester.tap(find.byIcon(Icons.search));
      await tester.pumpAndSettle();

      expect(find.text('Vasanthi Prabhu'), findsOneWidget);
      expect(find.textContaining('SUP-014'), findsOneWidget);
      expect(client.steps, isEmpty, reason: 'nothing identified yet');

      await tester.tap(find.text('Vasanthi Prabhu'));
      await tester.pumpAndSettle();

      final identify = client.steps.where((s) => s.$1.endsWith('/identify'));
      expect(identify, hasLength(1));
      expect(identify.single.$2, {'method': 'code', 'value': 'SUP-014'});
      // Step 2 — no second tap was needed.
      expect(find.text('Collection — step 2 of 6'), findsOneWidget);
    });

    testWidgets('search fires as you type, once the typing pauses', (
      tester,
    ) async {
      // WO-69. The magnifier was the only trigger: at a counter at 5am with a
      // queue behind the farmer, that tap was a wasted motion on the most
      // repeated action in the product. Now the pause does it — and ONLY the
      // pause: five keystrokes in quick succession are one request.
      final client = _Fake();
      await _pump(tester, client, step: 0);
      final box = find.widgetWithText(TextField, 'Search by name or phone');

      for (final partial in ['V', 'Va', 'Vas', 'Vasa', 'Vasan']) {
        await tester.enterText(box, partial);
        await tester.pump(const Duration(milliseconds: 100));
        expect(client.searches, 0, reason: 'still typing: no request yet');
      }
      await tester.pump(kLookupDebounce);
      await tester.pumpAndSettle();

      expect(client.searches, 1);
      expect(client.searchedQuery, 'Vasan');
      expect(find.text('Vasanthi Prabhu'), findsOneWidget);
    });

    testWidgets('clearing the box clears the list', (tester) async {
      final client = _Fake();
      await _pump(tester, client, step: 0);
      final box = find.widgetWithText(TextField, 'Search by name or phone');
      await tester.enterText(box, 'Vasanthi');
      await tester.pump(kLookupDebounce);
      await tester.pumpAndSettle();
      expect(find.text('Vasanthi Prabhu'), findsOneWidget);

      await tester.enterText(box, '');
      await tester.pump(kLookupDebounce);
      await tester.pumpAndSettle();
      expect(find.text('Vasanthi Prabhu'), findsNothing);
      expect(client.searches, 1, reason: 'an empty query is not a search');
    });

    testWidgets('the search is narrowed to THIS centre', (tester) async {
      // A dairy has hundreds of farmers and a counter serves dozens. Worse
      // than long: an unnarrowed list offers people who do not deliver here.
      final client = _Fake();
      await _pump(tester, client, step: 0);
      await tester.enterText(
        find.widgetWithText(TextField, 'Search by name or phone'),
        '9845',
      );
      await tester.tap(find.byIcon(Icons.search));
      await tester.pumpAndSettle();
      expect(client.searchedCentre, 'centre-1');
      expect(client.searchedQuery, '9845');
    });

    testWidgets('nothing found is said, not left blank', (tester) async {
      final client = _Fake(suppliers: const []);
      await _pump(tester, client, step: 0);
      await tester.enterText(
        find.widgetWithText(TextField, 'Search by name or phone'),
        'Nobody',
      );
      await tester.tap(find.byIcon(Icons.search));
      await tester.pumpAndSettle();
      expect(find.text('Nobody at this centre matches that'), findsOneWidget);
    });

    testWidgets('a transport failure says so rather than showing nothing', (
      tester,
    ) async {
      final client = _Fake(searchFails: true);
      await _pump(tester, client, step: 0);
      await tester.enterText(
        find.widgetWithText(TextField, 'Search by name or phone'),
        'Vasanthi',
      );
      await tester.tap(find.byIcon(Icons.search));
      await tester.pumpAndSettle();
      expect(find.textContaining('Could not reach'), findsOneWidget);
    });
  });
}
