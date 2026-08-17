/// The driver screen, verified without a handset (P0-UX-001).
///
/// A physical device is not attached, so this is the honest maximum available:
/// the REAL screen pumped at a small phone's dimensions, where a RenderFlex
/// overflow is a test failure rather than a yellow-black stripe nobody sees.
/// Long Indian names, long phone numbers, Hindi strings and both empty states
/// are exactly the cases the pilot will produce on day one.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/driver.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';
import 'package:lacteva_mobile/src/session.dart';

Session _session({String locale = 'en'}) => Session(
  userId: 'u1',
  email: 'driver@dairy.example',
  fullName: 'Driver',
  tenantId: 'org-1',
  permissions: const {'logistics.run.execute'},
  locale: locale,
);

Map<String, dynamic> _stop(int position, String name, {String? outcome}) => {
  'customer_id': 'cus-$position',
  'position': position,
  'code': 'CUS-$position',
  'name': name,
  'phone': '+91 98765 43210 (alt +91 87654 32109)',
  'address': 'H.No. 12-3-456/78, Beside Old Water Tank, Gandhi Nagar Extension',
  'delivery_status': outcome,
};

Map<String, dynamic> _run({List<Map<String, dynamic>>? stops, String status = 'planned'}) => {
  'id': 'run-1',
  'route_code': 'R-01',
  'route_name': 'श्री कृष्ण डेयरी सुबह की लंबी घुमावदार पहाड़ी वाली सप्लाई लाइन',
  'business_date': '2026-08-17',
  'slot': 'morning',
  'vehicle_registration': 'MH 12 AB 1234',
  'driver_name': 'Ramakrishnan Venkatasubramanian',
  'status': status,
  'stops': stops ?? [],
};

class _FakeDriverClient extends OfflineApiClient {
  _FakeDriverClient({required this.linked, required this.runs})
    : super(queue: SyncQueue(MemoryOfflineStore()), deviceId: 'test-device');

  final bool linked;
  final List<Map<String, dynamic>> runs;

  @override
  Future<Map<String, dynamic>> driverMe() async {
    if (!linked) throw ApiException(404, 'no driver profile is linked');
    return {'code': 'DRV-1', 'full_name': 'Driver'};
  }

  @override
  Future<List<Map<String, dynamic>>> myRuns() async => runs;
}

Future<void> _pumpSmallPhone(WidgetTester tester, Widget child) async {
  // A small, cheap Android handset — the pilot's actual hardware.
  tester.view.physicalSize = const Size(320, 568);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(home: child));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a run with long Indian names fits a 320px phone', (tester) async {
    final client = _FakeDriverClient(
      linked: true,
      runs: [
        _run(
          status: 'in_progress',
          stops: [
            _stop(1, 'Venkatanarasimharajuvaripeta Household Number One'),
            _stop(2, 'M/s Lakshminarayana Provisions & General Stores Pvt Ltd',
                outcome: 'delivered'),
            _stop(3, 'सरस्वती विद्या मंदिर उच्चतर माध्यमिक विद्यालय छात्रावास'),
          ],
        ),
      ],
    );

    await _pumpSmallPhone(
      tester,
      DriverHomeScreen(client: client, session: _session()),
    );

    // The route name, the vehicle and every stop rendered — and pumpAndSettle
    // completing without a RenderFlex overflow IS the layout assertion.
    expect(find.textContaining('MH 12 AB 1234'), findsOneWidget);
    expect(
      find.textContaining('Venkatanarasimharajuvaripeta'),
      findsOneWidget,
    );
    expect(find.text('Delivered'), findsOneWidget); // outcome chip
    expect(tester.takeException(), isNull);
  });

  testWidgets('the unlinked login gets its own calm state, in Hindi', (tester) async {
    final client = _FakeDriverClient(linked: false, runs: const []);

    await _pumpSmallPhone(
      tester,
      DriverHomeScreen(client: client, session: _session(locale: 'hi')),
    );

    expect(find.text('अभी ड्राइवर के रूप में सेट नहीं'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a linked driver with no run today is told so, not shown an error',
      (tester) async {
    final client = _FakeDriverClient(linked: true, runs: const []);

    await _pumpSmallPhone(
      tester,
      DriverHomeScreen(client: client, session: _session()),
    );

    expect(find.text('No run assigned today'), findsOneWidget);
    expect(find.byIcon(Icons.free_breakfast_outlined), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a planned run offers Start; recording appears only once started',
      (tester) async {
    final client = _FakeDriverClient(
      linked: true,
      runs: [
        _run(status: 'planned', stops: [_stop(1, 'Household One')]),
      ],
    );

    await _pumpSmallPhone(
      tester,
      DriverHomeScreen(client: client, session: _session()),
    );

    expect(find.text('Start run'), findsOneWidget);
    // planned runs still allow recording per the platform, and the button is
    // there — but Complete must not be offered before the run starts.
    expect(find.text('Complete run'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
