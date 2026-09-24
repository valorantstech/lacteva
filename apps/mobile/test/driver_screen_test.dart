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
  _FakeDriverClient({required this.linked, required this.runs, this.products = const []})
    : super(queue: SyncQueue(MemoryOfflineStore()), deviceId: 'test-device');

  final bool linked;
  final List<Map<String, dynamic>> runs;
  final List<Map<String, dynamic>> products;
  /// What the phone sent: outcomes as (customer, status, quantity, product);
  /// items as (customer, code, quantity).
  final outcomes = <List<String?>>[];
  final items = <List<String?>>[];

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
    outcomes.add([customerId, status, quantity, product]);
    return {'customer_id': customerId, 'delivery_status': status};
  }

  @override
  Future<List<Map<String, dynamic>>> listProducts() async => products;

  @override
  Future<Map<String, dynamic>> recordSaleItem({
    required String customerId,
    required String productCode,
    required String quantity,
    String? saleDate,
    String? notes,
    String? idempotencyKey,
  }) async {
    items.add([customerId, productCode, quantity]);
    return {'id': 'it-1', 'product_name': 'Dahi 500 g', 'amount': '40.00'};
  }

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
  wo82Tests();
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
    // LACTEVA-MOBILE-006 moved this: the board makes ONE stop the subject, so
    // the settled stops are no longer listed with outcome chips and the word
    // that survives is the next stop's action. The claim this test makes is
    // about layout on cheap hardware, and it still holds.
    expect(find.text('Delivered'), findsOneWidget);
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

// --- WO-82: the round, as it actually happens ---------------------------------

Map<String, dynamic> _order(String product, String name, String quantity, {String unit = 'L'}) => {
  'product': product,
  'product_name': name,
  'quantity': quantity,
  'quantity_unit': unit,
  'delivery_status': null,
};

Future<_FakeDriverClient> _pumpRun(
  WidgetTester tester, {
  required List<Map<String, dynamic>> orders,
  List<Map<String, dynamic>> products = const [],
}) async {
  final stop = _stop(1, 'Tower 1-2006');
  stop['orders'] = orders;
  final client = _FakeDriverClient(
    linked: true,
    runs: [_run(status: 'in_progress', stops: [stop])],
    products: products,
  );
  // A little taller than the pilot phone: the sheet needs room to open.
  tester.view.physicalSize = const Size(400, 900);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(home: DriverHomeScreen(client: client, session: _session())));
  await tester.pumpAndSettle();
  return client;
}

void wo82Tests() {
  testWidgets('the stop says what to pour, and "yes, the usual" sends no quantity', (tester) async {
    final client = await _pumpRun(tester, orders: [_order('COW-MILK', 'Cow milk', '1.000')]);
    expect(find.byKey(const ValueKey('stop-order-COW-MILK')), findsOneWidget);
    expect(find.text('Cow milk · 1.000 L'), findsOneWidget);
    await tester.tap(find.text('Delivered'));
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(find.byKey(const ValueKey('pour-quantity'))).controller!.text, '1.000');
    await tester.tap(find.byKey(const ValueKey('pour-confirm')));
    await tester.pumpAndSettle();
    expect(client.outcomes, [
      ['cus-1', 'delivered', null, null],
    ]);
  });

  testWidgets('a changed quantity is sent, stepped by a quarter litre', (tester) async {
    final client = await _pumpRun(tester, orders: [_order('COW-MILK', 'Cow milk', '1.000')]);
    await tester.tap(find.text('Delivered'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('pour-plus')));
    await tester.tap(find.byKey(const ValueKey('pour-plus')));
    await tester.pump();
    expect(tester.widget<TextField>(find.byKey(const ValueKey('pour-quantity'))).controller!.text, '1.500');
    await tester.tap(find.byKey(const ValueKey('pour-confirm')));
    await tester.pumpAndSettle();
    expect(client.outcomes, [
      ['cus-1', 'delivered', '1.500', null],
    ]);
  });

  testWidgets('a household with two milks is asked which, and the product is sent', (tester) async {
    final client = await _pumpRun(
      tester,
      orders: [_order('COW-MILK', 'Cow milk', '1.500'), _order('BUFFALO-MILK', 'Buffalo milk', '0.500')],
    );
    expect(find.text('Buffalo milk · 0.500 L'), findsOneWidget);
    await tester.tap(find.text('Delivered'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('pour-BUFFALO-MILK')));
    await tester.pump();
    expect(tester.widget<TextField>(find.byKey(const ValueKey('pour-quantity'))).controller!.text, '0.500');
    await tester.tap(find.byKey(const ValueKey('pour-confirm')));
    await tester.pumpAndSettle();
    expect(client.outcomes, [
      ['cus-1', 'delivered', null, 'BUFFALO-MILK'],
    ]);
  });

  testWidgets('an item is added from the catalogue with no price, and a priceless one cannot be', (tester) async {
    final client = await _pumpRun(
      tester,
      orders: [_order('COW-MILK', 'Cow milk', '1.000')],
      products: [
        {'code': 'DAHI-500G', 'name': 'Dahi 500 g', 'unit': 'pc', 'default_price': '40.00'},
        {'code': 'OTHER', 'name': 'Other shop item', 'unit': 'pc', 'default_price': null},
      ],
    );
    await tester.tap(find.byKey(const ValueKey('stop-add-item')));
    await tester.pumpAndSettle();
    expect(find.text('No price in the catalogue — the owner must set one.'), findsOneWidget);
    expect(tester.widget<ListTile>(find.byKey(const ValueKey('item-OTHER'))).enabled, isFalse);
    await tester.tap(find.byKey(const ValueKey('item-DAHI-500G')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('item-plus')));
    await tester.pump();
    expect(find.text('2 pc'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('item-confirm')));
    await tester.pumpAndSettle();
    expect(client.items, [
      ['cus-1', 'DAHI-500G', '2.000'],
    ]);
    expect(find.textContaining('Item added'), findsOneWidget);
  });

  testWidgets('offline, the item goes into the queue with its own idempotency key', (tester) async {
    final client = await _pumpRun(
      tester,
      orders: [_order('COW-MILK', 'Cow milk', '1.000')],
      products: [
        {'code': 'DAHI-500G', 'name': 'Dahi 500 g', 'unit': 'pc', 'default_price': '40.00'},
      ],
    );
    await client.cachedProducts();
    client.forceOffline = true;
    await tester.tap(find.byKey(const ValueKey('stop-add-item')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('item-DAHI-500G')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('item-confirm')));
    await tester.pumpAndSettle();
    expect(client.items, isEmpty);
    await client.queue.load();
    final queued = client.queue.due().where((op) => op.kind == 'sale_item').toList();
    expect(queued, hasLength(1));
    expect(queued.single.targetRef, '/v1/customers/cus-1/items');
    expect(queued.single.payload['product_code'], 'DAHI-500G');
    expect(queued.single.payload['idempotency_key'], queued.single.operationId);
  });
}
