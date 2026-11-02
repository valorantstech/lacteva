/// WO-110 · LACTEVA-MOBILE-017 — the round, walked on a real phone.
///
/// The owner recorded both stops of a two-stop round on a moto g57 and the
/// phone said "Run finished · 2 of 2 stops · Every stop recorded" while
/// B-204's buffalo milk sat scheduled at ₹0. These tests pin the phone's half
/// of the fix: a stop lists every standing order and records ALL of them,
/// progress counts deliveries, the finished round is a home with a summary and
/// reviewable stops, "Mark the rest" is one confirmed, queue-safe operation,
/// and "no round today" says when the next one is.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/driver.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';
import 'package:lacteva_mobile/src/session.dart';

Session _session({String locale = 'en'}) => Session(
  userId: 'u1',
  email: 'boy@patel.example',
  fullName: 'Mutahhar Pathan',
  tenantId: 'org-1',
  permissions: const {'logistics.run.execute'},
  locale: locale,
);

Map<String, dynamic> _order(
  String product,
  String name,
  String quantity, {
  String? status,
  String? delivered,
  bool invoiced = false,
}) => {
  'product': product,
  'product_name': name,
  'quantity': quantity,
  'quantity_unit': 'L',
  'delivery_status': status,
  'quantity_delivered': delivered,
  'invoiced': invoiced,
};

Map<String, dynamic> _stop(
  int position,
  String name,
  List<Map<String, dynamic>> orders, {
  List<Map<String, dynamic>> items = const [],
}) {
  final statuses = orders.map((o) => o['delivery_status']).toList();
  return {
    'customer_id': 'cus-$position',
    'position': position,
    'code': 'CUS-$position',
    'name': name,
    'phone': '',
    'address': 'Sunrise Tower, flat $position',
    'delivery_status': statuses.any((s) => s == null || s == 'scheduled')
        ? 'scheduled'
        : statuses.contains('delivered')
        ? 'delivered'
        : statuses.first,
    'orders': orders,
    'items': items,
  };
}

Map<String, dynamic> _run(String status, List<Map<String, dynamic>> stops) => {
  'id': 'run-1',
  'route_code': 'SUNRISE-TOWER-MORNING',
  'route_name': 'Sunrise Tower morning',
  'business_date': '2026-09-27',
  'slot': 'morning',
  'vehicle_registration': null,
  'driver_name': 'Mutahhar Pathan',
  'status': status,
  'transport': 'on_foot',
  'stops': stops,
};

class _Phone extends OfflineApiClient {
  _Phone({required this.runs, this.next})
    : super(queue: SyncQueue(MemoryOfflineStore()), deviceId: 'moto-g57');

  List<Map<String, dynamic>> runs;
  final Map<String, dynamic>? next;
  final outcomes = <List<String?>>[];
  final batches = <String>[];
  final transitions = <String>[];

  @override
  Future<Map<String, dynamic>> driverMe() async => {'code': 'MUTAHHAR-PATHAN'};

  @override
  Future<List<Map<String, dynamic>>> myRuns() async => runs;

  @override
  Future<Map<String, dynamic>> myNextRound() async => next ?? {'business_date': null};

  @override
  Future<Map<String, dynamic>> recordRunOutcome({
    required String runId,
    required String customerId,
    required String status,
    String? quantity,
    String? notes,
    String? product,
    String? idempotencyKey,
  }) async {
    outcomes.add([customerId, status, quantity, product, notes]);
    return {'customer_id': customerId, 'delivery_status': status};
  }

  @override
  Future<Map<String, dynamic>> markRemainingDelivered(String runId, {String? idempotencyKey}) async {
    batches.add(runId);
    return {'run_id': runId, 'marked': 2, 'untouched': 1};
  }

  @override
  Future<Map<String, dynamic>> completeMyRun(String runId) async {
    transitions.add('complete:$runId');
    return {'id': runId, 'status': 'completed'};
  }
}

Future<_Phone> _pump(
  WidgetTester tester, {
  required List<Map<String, dynamic>> runs,
  Map<String, dynamic>? next,
  Size size = const Size(360, 800),
}) async {
  final phone = _Phone(runs: runs, next: next);
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(home: DriverHomeScreen(client: phone, session: _session())),
  );
  await tester.pumpAndSettle();
  return phone;
}

final _a101 = _stop(1, 'A-101', [_order('COW-MILK', 'Cow milk', '1.000')]);
final _b204 = _stop(2, 'B-204', [
  _order('COW-MILK', 'Cow milk', '1.000'),
  _order('BUFFALO-MILK', 'Buffalo milk', '0.500'),
]);

void main() {
  group('§1 the second milk', () {
    testWidgets('the stop card shows both products, and Delivered records BOTH', (tester) async {
      final phone = await _pump(tester, runs: [_run('in_progress', [_b204, _a101])]);
      expect(find.byKey(const ValueKey('stop-order-COW-MILK')), findsOneWidget);
      expect(find.byKey(const ValueKey('stop-order-BUFFALO-MILK')), findsOneWidget);
      // Two stops, THREE deliveries.
      expect(find.text('0 of 3 deliveries'), findsOneWidget);
      expect(find.text('3 deliveries remaining'), findsOneWidget);

      await tester.tap(find.text('Delivered'));
      await tester.pumpAndSettle();
      // The buffalo is adjusted at the door; the cow is the usual.
      await tester.tap(find.byKey(const ValueKey('pour-plus-BUFFALO-MILK')));
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('pour-confirm')));
      await tester.pumpAndSettle();
      expect(phone.outcomes, [
        ['cus-2', 'delivered', null, 'COW-MILK', null],
        ['cus-2', 'delivered', '0.750', 'BUFFALO-MILK', null],
      ]);
    });

    testWidgets('"took the cow, not the buffalo today": one delivered, one skipped', (tester) async {
      final phone = await _pump(tester, runs: [_run('in_progress', [_b204])]);
      await tester.tap(find.text('Delivered'));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('pour-skip-BUFFALO-MILK')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('pour-skipped-BUFFALO-MILK')), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('pour-confirm')));
      await tester.pumpAndSettle();
      expect(phone.outcomes, [
        ['cus-2', 'delivered', null, 'COW-MILK', null],
        ['cus-2', 'skipped', null, 'BUFFALO-MILK', 'skipped at the gate'],
      ]);
    });

    testWidgets('a stop with one milk recorded is still the stop in front of him', (tester) async {
      final half = _stop(2, 'B-204', [
        _order('COW-MILK', 'Cow milk', '1.000', status: 'delivered', delivered: '1.000'),
        _order('BUFFALO-MILK', 'Buffalo milk', '0.500'),
      ]);
      final done = _stop(1, 'A-101', [
        _order('COW-MILK', 'Cow milk', '1.000', status: 'delivered', delivered: '1.000'),
      ]);
      final phone = await _pump(tester, runs: [_run('in_progress', [done, half])]);
      expect(find.text('NEXT STOP'), findsOneWidget);
      expect(find.text('B-204'), findsOneWidget);
      expect(find.text('2 of 3 deliveries'), findsOneWidget);
      expect(find.text('1 delivery remaining'), findsOneWidget);
      // The run is NOT offered for completion: one delivery is still open.
      expect(find.text('Complete run'), findsNothing);
      // Delivered now asks only about the buffalo, and sends only it. (By
      // key: the recorded cow wears a "Delivered" pill on the card.)
      await tester.tap(find.byKey(const ValueKey('stop-delivered')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('pour-quantity')), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('pour-confirm')));
      await tester.pumpAndSettle();
      expect(phone.outcomes, [
        ['cus-2', 'delivered', null, 'BUFFALO-MILK', null],
      ]);
    });

    testWidgets('Missed skips every open delivery at the door', (tester) async {
      final phone = await _pump(tester, runs: [_run('in_progress', [_b204])]);
      await tester.tap(find.text('Missed'));
      await tester.pumpAndSettle();
      expect(phone.outcomes.map((o) => '${o[1]}:${o[3]}').toList(), [
        'skipped:COW-MILK',
        'skipped:BUFFALO-MILK',
      ]);
    });
  });

  group('§4 mark the rest as delivered', () {
    testWidgets('one confirmation that states the count, then one call', (tester) async {
      final phone = await _pump(tester, runs: [_run('in_progress', [_a101, _b204])]);
      await tester.tap(find.byKey(const ValueKey('mark-rest')));
      await tester.pumpAndSettle();
      expect(
        find.textContaining('Mark 3 remaining deliveries as delivered with the usual quantity?'),
        findsOneWidget,
      );
      await tester.tap(find.byKey(const ValueKey('mark-rest-cancel')));
      await tester.pumpAndSettle();
      expect(phone.batches, isEmpty);

      await tester.tap(find.byKey(const ValueKey('mark-rest')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('mark-rest-confirm')));
      await tester.pumpAndSettle();
      expect(phone.batches, ['run-1']);
      expect(find.text('2 deliveries marked delivered'), findsOneWidget);
    });

    test('offline, it is ONE queued operation addressed to the run', () async {
      final phone = _Phone(runs: const [])..forceOffline = true;
      final result = await phone.markRemainingDeliveredOffline(runId: 'run-1');
      expect(result['_queued'], isTrue);
      expect(phone.batches, isEmpty);
      await phone.queue.load();
      final queued = phone.queue.due().where((op) => op.kind == 'run_remaining').toList();
      expect(queued, hasLength(1));
      expect(queued.single.targetRef, '/v1/delivery-runs/run-1/outcomes/remaining');
      expect(phone.pendingCount, 1);
    });
  });

  group('§2 the Round tab is a home in every state', () {
    testWidgets('before the run: what to carry, and every stop', (tester) async {
      await _pump(tester, runs: [_run('planned', [_a101, _b204])]);
      expect(find.text('TO CARRY'), findsOneWidget);
      expect(find.byKey(const ValueKey('carry-Cow milk')), findsOneWidget);
      expect(find.text('2 L'), findsOneWidget);
      expect(find.text('0.5 L'), findsOneWidget);
      expect(find.text("TODAY'S STOPS"), findsOneWidget);
      expect(find.text('Start run'), findsOneWidget);
    });

    testWidgets('after the run: the day in figures, every stop openable, back works', (tester) async {
      final finished = _run('completed', [
        _stop(1, 'A-101', [
          _order('COW-MILK', 'Cow milk', '1.000', status: 'delivered', delivered: '1.500'),
        ], items: [
          {'product': 'DAHI-500-G', 'product_name': 'Dahi 500 g', 'quantity': '2.000', 'unit': 'pc'},
        ]),
        _stop(2, 'B-204', [
          _order('COW-MILK', 'Cow milk', '1.000', status: 'delivered', delivered: '1.000'),
          _order('BUFFALO-MILK', 'Buffalo milk', '0.500', status: 'delivered', delivered: '0.500', invoiced: true),
        ]),
        _stop(3, 'C-305', [_order('COW-MILK', 'Cow milk', '1.000', status: 'skipped')]),
      ]);
      final phone = await _pump(tester, runs: [finished]);
      expect(find.text('Run finished'), findsOneWidget);
      expect(find.text('4 of 4 deliveries'), findsOneWidget);
      expect(find.byKey(const ValueKey('delivered-Cow milk')), findsOneWidget);
      expect(find.text('2.5 L'), findsOneWidget); // 1.5 + 1.0, what actually went
      expect(find.byKey(const ValueKey('sold-Dahi 500 g')), findsOneWidget);
      expect(find.text('2 pc'), findsOneWidget);
      expect(find.text('Stops skipped'), findsOneWidget);
      // Nothing to record any more — but every stop can be OPENED.
      expect(find.text('Delivered'), findsNothing);
      await tester.tap(find.byKey(const ValueKey('review-cus-2')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('review-back')), findsOneWidget);
      // The cow may be corrected; the buffalo is on a bill and may not.
      expect(find.byKey(const ValueKey('correct-COW-MILK')), findsOneWidget);
      expect(find.byKey(const ValueKey('correct-BUFFALO-MILK')), findsNothing);
      expect(find.byKey(const ValueKey('on-bill-BUFFALO-MILK')), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('correct-COW-MILK')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('pour-plus')));
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('pour-confirm')));
      await tester.pumpAndSettle();
      expect(phone.outcomes, [
        ['cus-2', 'delivered', '1.250', 'COW-MILK', null],
      ]);
      // The arrow goes back to the Round tab.
      await tester.tap(find.byKey(const ValueKey('review-back')));
      await tester.pumpAndSettle();
      expect(find.text('Run finished'), findsOneWidget);
    });

    testWidgets('after the run, tomorrow is announced when it is planned', (tester) async {
      final tomorrow = DateTime.now().add(const Duration(days: 1));
      final iso = '${tomorrow.year}-${tomorrow.month.toString().padLeft(2, '0')}-${tomorrow.day.toString().padLeft(2, '0')}';
      await _pump(
        tester,
        runs: [_run('completed', [_stop(1, 'A-101', [_order('COW-MILK', 'Cow milk', '1.000', status: 'delivered')])])],
        next: {'business_date': iso, 'stops': 2, 'planned': true},
      );
      expect(find.text('Tomorrow: 2 stops'), findsOneWidget);
    });

    testWidgets('no run today: calm, with the next planned date', (tester) async {
      await _pump(tester, runs: const [], next: {'business_date': '2030-01-07', 'stops': 5, 'planned': false});
      expect(find.text('No round today'), findsOneWidget);
      expect(find.textContaining('Next round:'), findsOneWidget);
      expect(find.textContaining('5 stops'), findsOneWidget);
    });

    testWidgets('no run today and nothing known: no invented date', (tester) async {
      await _pump(tester, runs: const []);
      expect(find.text('No round today'), findsOneWidget);
      expect(find.textContaining('Next round'), findsNothing);
      expect(find.text('When the office plans your round, it appears here.'), findsOneWidget);
    });

    testWidgets('a Hindi delivery boy reads the same screen in Hindi', (tester) async {
      final phone = _Phone(runs: [_run('in_progress', [_b204])]);
      tester.view.physicalSize = const Size(360, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(home: DriverHomeScreen(client: phone, session: _session(locale: 'hi'))),
      );
      await tester.pumpAndSettle();
      expect(find.text('2 में से 0 डिलीवरी'), findsOneWidget);
      expect(find.text('बाक़ी सब दिया गया दर्ज करें'), findsOneWidget);
    });
  });
}
