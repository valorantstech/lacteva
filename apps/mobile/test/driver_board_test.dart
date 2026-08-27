/// The driver board (LACTEVA-MOBILE-006; board: Driver.dc.html).
///
/// Glanceability is the design constraint here in a way it is nowhere else in
/// the product: this screen is read through a windscreen, with the engine
/// running, by somebody who will look away again in two seconds. So what is
/// pinned is not "it renders" but the hierarchy — ONE stop is the subject, the
/// rest is queue, and the two decisions about the stop in front of the van are
/// full-height targets that do not move.
///
/// The data path is untouched by this work order. Outcomes still go through
/// the same durable queue with the same statuses, and start/complete are still
/// the platform's own transitions — the tests below name them so a redesign
/// cannot quietly change what a tap records.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/driver.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';
import 'package:lacteva_mobile/src/offline/sync_engine.dart';
import 'package:lacteva_mobile/src/session.dart';
import 'package:lacteva_mobile/src/theme.dart';

/// A stop exactly as `RunStopView` sends one — no quantity, because the model
/// has none and the tests must not pretend otherwise.
Map<String, dynamic> _stop(
  int position,
  String name, {
  String? outcome,
  String address = '',
}) => <String, dynamic>{
  'customer_id': 'c$position',
  'position': position,
  'code': 'H-00$position',
  'name': name,
  'phone': '',
  'address': address,
  'delivery_status': outcome,
};

Map<String, dynamic> _run({
  required String status,
  required List<Map<String, dynamic>> stops,
  String slot = 'morning',
}) => <String, dynamic>{
  'id': 'run-1',
  'route_id': 'rt-1',
  'route_code': 'R-3',
  'route_name': 'Route 3 · West Ward',
  'business_date': '2026-08-27',
  'slot': slot,
  'vehicle_id': 'v1',
  'vehicle_registration': 'MH 12 KA 4471',
  'driver_id': 'd1',
  'driver_name': 'Driver',
  'status': status,
  'notes': '',
  'stops': stops,
};

class _Platform extends ApiClient {
  _Platform({required this.runs, this.linked = true});

  final List<Map<String, dynamic>> runs;
  final bool linked;

  /// What the screen actually asked the platform to record.
  final List<String> recorded = [];
  final List<String> transitions = [];

  @override
  Future<Map<String, dynamic>> driverMe() async {
    if (!linked) throw ApiException(404, 'no driver profile');
    return {'code': 'DRV-1', 'full_name': 'Driver'};
  }

  @override
  Future<List<Map<String, dynamic>>> myRuns() async => runs;

  @override
  Future<Map<String, dynamic>> recordRunOutcome({
    required String runId,
    required String customerId,
    required String status,
    String? quantity,
    String? notes,
    String? idempotencyKey,
  }) async {
    // Quantity is recorded here rather than read: a driver may report what
    // actually went off the van, but nothing tells the app what was PLANNED.
    recorded.add('$customerId:$status:${quantity ?? ""}:${notes ?? ""}');
    return {'ok': true};
  }

  @override
  Future<Map<String, dynamic>> startMyRun(String runId) async {
    transitions.add('start:$runId');
    return {'id': runId, 'status': 'in_progress'};
  }

  @override
  Future<Map<String, dynamic>> completeMyRun(String runId) async {
    transitions.add('complete:$runId');
    return {'id': runId, 'status': 'completed'};
  }
}

/// The real offline client over the fake platform — the same seam the app
/// uses, so a recorded outcome travels the queue it travels in the field.
class _Client extends OfflineApiClient {
  _Client(this.platform, SyncQueue queue)
    : super(
        queue: queue,
        deviceId: 'test-device',
        engine: SyncEngine(
          client: platform,
          queue: queue,
          deviceId: 'test-device',
        ),
      );

  final _Platform platform;

  @override
  Future<Map<String, dynamic>> driverMe() => platform.driverMe();

  @override
  Future<List<Map<String, dynamic>>> myRuns() => platform.myRuns();

  @override
  Future<Map<String, dynamic>> startMyRun(String runId) =>
      platform.startMyRun(runId);

  @override
  Future<Map<String, dynamic>> completeMyRun(String runId) =>
      platform.completeMyRun(runId);

  @override
  Future<Map<String, dynamic>> recordRunOutcome({
    required String runId,
    required String customerId,
    required String status,
    String? quantity,
    String? notes,
    String? idempotencyKey,
  }) => platform.recordRunOutcome(
    runId: runId,
    customerId: customerId,
    status: status,
    quantity: quantity,
    notes: notes,
    idempotencyKey: idempotencyKey,
  );
}

Session _session({String locale = 'en'}) => Session(
  userId: 'u1',
  email: 'driver@dairy.example',
  fullName: 'Ramesh Patil',
  tenantId: 'org-1',
  // DRIVER's real grant list from the platform's registry — exactly one key.
  permissions: const {'logistics.run.execute'},
  locale: locale,
);

Future<_Platform> _pump(
  WidgetTester tester, {
  required List<Map<String, dynamic>> runs,
  bool linked = true,
  String locale = 'en',
  Size size = const Size(390, 844),
}) async {
  final platform = _Platform(runs: runs, linked: linked);
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: lactevaTheme(),
      home: DriverHomeScreen(
        key: UniqueKey(),
        client: _Client(platform, SyncQueue(MemoryOfflineStore())),
        session: _session(locale: locale),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return platform;
}

void main() {
  group('the run header', () {
    testWidgets('says which round, on what, and how far along', (tester) async {
      await _pump(
        tester,
        runs: [
          _run(
            status: 'in_progress',
            stops: [
              _stop(1, 'Hotel Annapurna', outcome: 'delivered'),
              _stop(2, 'Café Madhuban', outcome: 'delivered'),
              _stop(3, 'Deshmukh household'),
              _stop(4, 'Shree Tea House'),
            ],
          ),
        ],
      );
      expect(find.text('Morning round'), findsOneWidget);
      // The header answers which round and how far; the band answers which
      // van. Each fact appears once, in the region that owns it.
      expect(find.text('Route 3 · West Ward'), findsOneWidget);
      expect(find.text('MH 12 KA 4471'), findsOneWidget);
      expect(find.text('2 of 4 stops'), findsOneWidget);
    });

    testWidgets('the chip says the run STATE, not a wall-clock time', (
      tester,
    ) async {
      // `started_at` is a UTC instant and this app performs no timezone
      // arithmetic — a driver in Pune must not read 00:34 for a 06:04 start.
      await _pump(
        tester,
        runs: [
          _run(status: 'in_progress', stops: [_stop(1, 'Household One')]),
        ],
      );
      expect(find.text('Run in progress'), findsOneWidget);
    });

    testWidgets('the progress bar reports the same fraction it draws', (
      tester,
    ) async {
      await _pump(
        tester,
        runs: [
          _run(
            status: 'in_progress',
            stops: [
              _stop(1, 'One', outcome: 'delivered'),
              _stop(2, 'Two'),
              _stop(3, 'Three'),
              _stop(4, 'Four'),
            ],
          ),
        ],
      );
      // Colour is never the only signal, and a bar is only colour.
      expect(
        tester
            .widgetList<Semantics>(find.byType(Semantics))
            .any((s) => s.properties.value == '1 / 4'),
        isTrue,
      );
    });
  });

  group('the next-stop card', () {
    testWidgets('makes ONE stop the subject and the rest the queue', (
      tester,
    ) async {
      await _pump(
        tester,
        runs: [
          _run(
            status: 'in_progress',
            stops: [
              _stop(1, 'Hotel Annapurna', address: '14, Lakshmi Road'),
              _stop(2, 'Café Madhuban'),
              _stop(3, 'Deshmukh household'),
            ],
          ),
        ],
      );
      expect(find.text('NEXT STOP'), findsOneWidget);
      expect(find.text('Hotel Annapurna'), findsOneWidget);
      expect(find.text('14, Lakshmi Road'), findsOneWidget);
      // The board's 40px figure. A run stop carries no quantity, so the big
      // number is the position — the thing a driver checks against a list.
      expect(find.text('Stop 1'), findsOneWidget);
      expect(find.text('of 3 stops'), findsOneWidget);
      // Everything after it is the queue, under its own label.
      expect(find.text('THEN'), findsOneWidget);
      expect(find.text('Café Madhuban'), findsOneWidget);
    });

    testWidgets('both decisions are full 56dp targets', (tester) async {
      // The hands work here. LactevaMetrics.primaryActionHeight is the house
      // number for "what do I press next" and it must not be negotiated down
      // by a two-button row.
      await _pump(
        tester,
        runs: [
          _run(status: 'in_progress', stops: [_stop(1, 'Hotel Annapurna')]),
        ],
      );
      for (final label in ['Delivered', 'Missed']) {
        final box = tester.getSize(
          find.ancestor(
            of: find.text(label),
            matching: find.byType(SizedBox),
          ).first,
        );
        expect(
          box.height,
          LactevaMetrics.primaryActionHeight,
          reason: label,
        );
      }
    });

    testWidgets('Delivered records delivered, for THIS stop', (tester) async {
      final platform = await _pump(
        tester,
        runs: [
          _run(
            status: 'in_progress',
            stops: [
              _stop(1, 'Hotel Annapurna', outcome: 'delivered'),
              _stop(2, 'Café Madhuban'),
            ],
          ),
        ],
      );
      await tester.tap(find.text('Delivered'));
      await tester.pumpAndSettle();
      // The SECOND stop is the open one, and its id is what was recorded.
      expect(platform.recorded, ['c2:delivered::']);
    });

    testWidgets('Missed records skipped, with the note it always carried', (
      tester,
    ) async {
      // Outcome semantics are untouched by this work order: the board's word
      // is "Missed", the platform's status is still `skipped`, and the default
      // note is the one the sheet has always sent.
      final platform = await _pump(
        tester,
        runs: [
          _run(status: 'in_progress', stops: [_stop(1, 'Hotel Annapurna')]),
        ],
      );
      await tester.tap(find.text('Missed'));
      await tester.pumpAndSettle();
      expect(platform.recorded, ['c1:skipped::skipped at the gate']);
    });

    testWidgets('a long Indian name and a 320px phone do not fight', (
      tester,
    ) async {
      // The pilot's actual hardware. pumpAndSettle completing without a
      // RenderFlex overflow IS the assertion — big type is only glanceable if
      // it survives the names this dairy actually has.
      await _pump(
        tester,
        size: const Size(320, 568),
        runs: [
          _run(
            status: 'in_progress',
            stops: [
              _stop(
                1,
                'M/s Lakshminarayana Provisions & General Stores Pvt Ltd',
                address: 'Plot 14B, Lakshmi Road, behind the old water tank',
              ),
              _stop(2, 'सरस्वती विद्या मंदिर उच्चतर माध्यमिक विद्यालय छात्रावास'),
            ],
          ),
        ],
      );
      expect(find.textContaining('Lakshminarayana'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group('the on-board band', () {
    testWidgets('offers Start before the run begins', (tester) async {
      final platform = await _pump(
        tester,
        runs: [
          _run(status: 'planned', stops: [_stop(1, 'Household One')]),
        ],
      );
      expect(find.text('Start run'), findsOneWidget);
      expect(find.text('Complete run'), findsNothing);
      await tester.tap(find.text('Start run'));
      await tester.pumpAndSettle();
      expect(platform.transitions, ['start:run-1']);
    });

    testWidgets('offers End only once every stop is recorded', (tester) async {
      await _pump(
        tester,
        runs: [
          _run(
            status: 'in_progress',
            stops: [
              _stop(1, 'One', outcome: 'delivered'),
              _stop(2, 'Two'),
            ],
          ),
        ],
      );
      expect(find.text('Complete run'), findsNothing);
      expect(find.text('1 stops remaining'), findsOneWidget);

      final platform = await _pump(
        tester,
        runs: [
          _run(
            status: 'in_progress',
            stops: [
              _stop(1, 'One', outcome: 'delivered'),
              _stop(2, 'Two', outcome: 'skipped'),
            ],
          ),
        ],
      );
      expect(find.text('Complete run'), findsOneWidget);
      expect(find.text('Every stop recorded'), findsOneWidget);
      await tester.tap(find.text('Complete run'));
      await tester.pumpAndSettle();
      expect(platform.transitions, ['complete:run-1']);
    });

    testWidgets('claims nothing about the load it cannot read', (tester) async {
      // The board carried "387 L on board · Loaded 06:00". A run has no
      // quantity, and `logistics.run.execute` is every grant a DRIVER holds —
      // there is no read that could ever supply one, so the band says what the
      // run is instead of inventing a figure.
      await _pump(
        tester,
        runs: [
          _run(status: 'in_progress', stops: [_stop(1, 'One')]),
        ],
      );
      expect(find.textContaining('on board'), findsNothing);
      expect(find.textContaining('Loaded'), findsNothing);
      // What it says instead: the van, and how much of the run is left.
      expect(find.text('MH 12 KA 4471'), findsOneWidget);
    });
  });

  group('what the redesign did not touch', () {
    testWidgets('the unlinked login still gets its own calm state', (
      tester,
    ) async {
      await _pump(tester, runs: const [], linked: false, locale: 'hi');
      expect(find.text('अभी ड्राइवर के रूप में सेट नहीं'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a linked driver with no run is told so, not shown an error', (
      tester,
    ) async {
      await _pump(tester, runs: const []);
      expect(find.text('No run assigned today'), findsOneWidget);
      expect(find.byIcon(Icons.free_breakfast_outlined), findsOneWidget);
    });

    testWidgets('a finished run offers no way to record anything', (
      tester,
    ) async {
      await _pump(
        tester,
        runs: [
          _run(
            status: 'completed',
            stops: [_stop(1, 'One', outcome: 'delivered')],
          ),
        ],
      );
      expect(find.text('Delivered'), findsNothing);
      expect(find.text('Missed'), findsNothing);
      expect(find.text('Run finished'), findsOneWidget);
    });

    testWidgets('a Hindi driver reads Hindi, from the same keys', (
      tester,
    ) async {
      await _pump(
        tester,
        locale: 'hi',
        runs: [
          _run(status: 'in_progress', stops: [_stop(1, 'Household One')]),
        ],
      );
      expect(find.text('अगला पड़ाव'.toUpperCase()), findsOneWidget);
      expect(find.text('छूट गया'), findsOneWidget);
      expect(find.text('Missed'), findsNothing);
    });
  });

  group('nothing on the action path animates', () {
    testWidgets('the board is still once it has loaded', (tester) async {
      await _pump(
        tester,
        runs: [
          _run(status: 'in_progress', stops: [_stop(1, 'Hotel Annapurna')]),
        ],
      );
      expect(tester.binding.hasScheduledFrame, isFalse);
    });
  });
}
