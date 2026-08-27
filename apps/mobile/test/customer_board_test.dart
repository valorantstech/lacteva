/// The household home (LACTEVA-MOBILE-007; board: Customer.dc.html).
///
/// A household opens this once a day to be reassured, not to work — which is
/// why it is the one screen in the product with an ambient animation, and why
/// its empty state has to welcome rather than apologise. A family whose first
/// delivery has not arrived yet has lost nothing; a screen that says "no
/// invoices" tells them something has gone wrong.
///
/// **Read-only stays read-only.** `CUSTOMER_PORTAL` holds five read grants and
/// nothing else, and the platform narrows every one of them to this household.
/// The fake below therefore implements reads only: a screen that tried to
/// write would fail to compile against it.
///
/// Three states are pinned — paid up, amount due, and a first month with
/// nothing in it — plus the reduced-motion switch, because an ambient
/// animation that ignores it is an accessibility fault rather than a flourish.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/customer_portal.dart';
import 'package:lacteva_mobile/src/session.dart';
import 'package:lacteva_mobile/src/theme.dart';

class _Platform extends ApiClient {
  _Platform({
    this.balance = const {'outstanding': '0.00', 'currency': 'INR'},
    this.plans = const [],
    this.deliveries = const [],
    this.invoices = const [],
    this.month,
  });

  final Map<String, dynamic> balance;
  final List<Map<String, dynamic>> plans;
  final List<Map<String, dynamic>> deliveries;
  final List<Map<String, dynamic>> invoices;
  final Map<String, dynamic>? month;

  final List<String> calls = [];

  @override
  Future<Map<String, dynamic>> customerDetail(String id) async {
    calls.add('customerDetail');
    return <String, dynamic>{
      'customer': <String, dynamic>{
        'id': id,
        'name': 'Deshmukh household',
        'code': 'H-001',
        'customer_type': 'household',
      },
      'plans': plans,
    };
  }

  @override
  Future<Map<String, dynamic>> customerBalance(String id) async {
    calls.add('customerBalance');
    return balance;
  }

  @override
  Future<Map<String, dynamic>> listDeliveries({
    String? customerId,
    String? dateFrom,
    String? dateTo,
    String? status,
    bool? invoiced,
    int limit = 20,
    int offset = 0,
  }) async {
    calls.add('listDeliveries');
    return <String, dynamic>{'items': deliveries, 'total': deliveries.length};
  }

  @override
  Future<Map<String, dynamic>> listInvoices({
    String? customerId,
    String? status,
    int limit = 20,
    int offset = 0,
  }) async {
    calls.add('listInvoices');
    return <String, dynamic>{'items': invoices, 'total': invoices.length};
  }

  @override
  Future<Map<String, dynamic>> listCustomerReceipts({
    String? customerId,
    int limit = 20,
    int offset = 0,
  }) async {
    calls.add('listCustomerReceipts');
    return <String, dynamic>{'items': const [], 'total': 0};
  }

  @override
  Future<Map<String, dynamic>> deliveryReport({
    String? dateFrom,
    String? dateTo,
    String? customerId,
  }) async {
    calls.add('deliveryReport');
    final m = month;
    if (m == null) throw ApiException(403, 'no delivery read');
    return m;
  }
}

Session _session({String locale = 'en'}) => Session(
  userId: 'u1',
  email: 'household@example.com',
  fullName: 'Deshmukh',
  tenantId: 'org-1',
  customerId: 'cust-1',
  locale: locale,
  // CUSTOMER_PORTAL's real grants, from the platform's own registry. Reads
  // only, every one of them narrowed to this household server-side.
  permissions: const {
    'sales.customer.read',
    'sales.delivery.read',
    'sales.invoice.read',
    'sales.payment.read',
    'sales.receipt.read',
  },
  organization: const OrgLocale(
    name: 'Sitara Dairy',
    countryCode: 'IN',
    currencyCode: 'INR',
    currencySymbol: '₹',
    timezone: 'Asia/Kolkata',
    defaultLanguage: 'en',
    supportedLanguages: ['en', 'hi'],
  ),
);

/// A month as `/v1/deliveries/report` sends it, narrowed to this household.
Map<String, dynamic> _month({
  String delivered = '54.000',
  String? expected = '62.000',
  String today = '2026-08-26',
}) => <String, dynamic>{
  'date_from': '2026-08-01',
  'date_to': today,
  'deliveries': 26,
  'customers_served': 1,
  'planned': 31,
  'planned_quantity': ?expected,
  'total_quantity': delivered,
  'quantity_unit': 'L',
  'total_amount': '3024.00',
};

Map<String, dynamic> _delivery(String date, {String quantity = '2.000'}) =>
    <String, dynamic>{
      'customer_id': 'cust-1',
      'delivery_date': date,
      'slot': 'morning',
      'status': 'delivered',
      'quantity': quantity,
      'quantity_unit': 'L',
      'amount': '112.00',
      'invoice_id': null,
    };

/// Pump, then advance a fixed amount.
///
/// NEVER `pumpAndSettle`: the mark shimmers forever by design, and a settle
/// would simply time out. That is the point of the animation and the reason
/// this helper exists.
Future<_Platform> _pump(
  WidgetTester tester, {
  _Platform? platform,
  Session? session,
  bool reducedMotion = false,
  Size size = const Size(390, 844),
}) async {
  final fake = platform ?? _Platform();
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: lactevaTheme(),
      home: MediaQuery(
        data: MediaQueryData(disableAnimations: reducedMotion),
        child: CustomerHomeScreen(
          key: UniqueKey(),
          client: fake,
          session: session ?? _session(),
        ),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
  return fake;
}

/// The vessel, if one is drawn at all.
///
/// The widget tree rather than the semantics tree: `bySemanticsLabel` reads
/// the latter, which a plain `pump` has not built, and an assertion that
/// silently finds nothing is worse than no assertion — this one is meant to
/// FAIL when a vessel appears.
Iterable<Semantics> _vessel(WidgetTester tester) => tester
    .widgetList<Semantics>(find.byType(Semantics))
    .where((s) => s.properties.label == 'Milk delivered this month');

/// Days drawn as still-to-come, by the painter that outlines them.
int _dashedDays(WidgetTester tester) => tester
    .widgetList<CustomPaint>(find.byType(CustomPaint))
    .where((c) => c.painter?.runtimeType.toString() == '_DashedBox')
    .length;

/// The seven day cells, by their own semantics.
///
/// The strip's figures also appear in the history below it, so a bare text
/// finder counts both. Each cell announces its day and what arrived on it,
/// which is the same information a sighted reader gets from the pairing.
Iterable<Semantics> _dayCells(WidgetTester tester) => tester
    .widgetList<Semantics>(find.byType(Semantics))
    .where(
      (s) => const [
        'Mon',
        'Tue',
        'Wed',
        'Thu',
        'Fri',
        'Sat',
        'Sun',
      ].contains(s.properties.label),
    );

void main() {
  group('the week, as calendar arithmetic and nothing more', () {
    test('runs Monday to Sunday around the day it is given', () {
      // 2026-08-26 is a Wednesday.
      expect(weekOf('2026-08-26'), [
        '2026-08-24',
        '2026-08-25',
        '2026-08-26',
        '2026-08-27',
        '2026-08-28',
        '2026-08-29',
        '2026-08-30',
      ]);
    });

    test('crosses a month boundary without losing a day', () {
      expect(weekOf('2026-09-01').first, '2026-08-31');
      expect(weekOf('2026-09-01').length, 7);
    });

    test('names only the two days a household thinks in', () {
      expect(relativeDayKey('2026-08-26', '2026-08-26'), 'customer.today');
      expect(relativeDayKey('2026-08-27', '2026-08-26'), 'customer.tomorrow');
      // Anything further out is rendered as the platform's own date rather
      // than counted into a sentence.
      expect(relativeDayKey('2026-08-28', '2026-08-26'), isNull);
      expect(relativeDayKey(null, '2026-08-26'), isNull);
    });

    test('only an ACTIVE plan may promise milk', () {
      // An inactive plan is a record of what used to happen. A card built from
      // one would tell a household to expect a delivery nobody will make.
      expect(activePlan(const []), isNull);
      expect(
        activePlan(const [
          {'id': 'p1', 'active': false},
        ]),
        isNull,
      );
      expect(
        activePlan(const [
          {'id': 'p1', 'active': false},
          {'id': 'p2', 'active': true},
        ])?['id'],
        'p2',
      );
    });
  });

  group('paid up', () {
    testWidgets('leads with the month, then says nothing is owed', (
      tester,
    ) async {
      await _pump(
        tester,
        platform: _Platform(
          month: _month(),
          balance: const {'outstanding': '0.00', 'currency': 'INR'},
        ),
      );
      expect(find.text('Deshmukh household'), findsOneWidget);
      expect(find.text('Your milk, this month'), findsOneWidget);
      // The platform's own decimal strings, both of them.
      expect(find.text('54.000 L'), findsOneWidget);
      expect(find.text('delivered of ~62.000 L this month'), findsOneWidget);
      expect(find.text('₹0.00 due'), findsOneWidget);
      // Never colour alone: the lighter green is the second signal, and the
      // sentence is the first.
      expect(find.text('Everything is paid up'), findsOneWidget);
    });

    testWidgets('the vessel reports the fraction it draws', (tester) async {
      await _pump(tester, platform: _Platform(month: _month()));
      // 54 of 62 ≈ 87%. The percentage is a LAYOUT figure announced to a
      // screen reader; the numbers on screen stay the platform's strings.
      expect(_vessel(tester).single.properties.value, '87%');
    });

    testWidgets('an invoice already settled says Paid, with its amount', (
      tester,
    ) async {
      await _pump(
        tester,
        platform: _Platform(
          month: _month(),
          invoices: const [
            {
              'id': 'inv-1',
              'invoice_number': 'INV-2026-07-0042',
              'period_from': '2026-07-01',
              'period_to': '2026-07-31',
              'amount_due': '0.00',
              'currency': 'INR',
              'status': 'paid',
              'line_count': 30,
            },
          ],
        ),
      );
      expect(find.text('INV-2026-07-0042'), findsOneWidget);
      expect(
        find.text('2026-07-01 → 2026-07-31 · 30 deliveries listed'),
        findsOneWidget,
      );
      expect(find.text('Paid'), findsOneWidget);
    });
  });

  group('amount due', () {
    testWidgets('states the amount and which invoice it is on', (tester) async {
      await _pump(
        tester,
        platform: _Platform(
          month: _month(),
          balance: const {'outstanding': '3360.00', 'currency': 'INR'},
          invoices: const [
            {
              'id': 'inv-2',
              'invoice_number': 'INV-2026-08-0051',
              'period_from': '2026-08-01',
              'period_to': '2026-08-31',
              'amount_due': '3360.00',
              'currency': 'INR',
              'status': 'issued',
              'line_count': 26,
            },
          ],
        ),
      );
      // The currency symbol is the ORGANIZATION's, not a country this app
      // believes it is in.
      expect(find.text('₹3360.00 due'), findsOneWidget);
      expect(find.text('on invoice INV-2026-08-0051'), findsOneWidget);
      expect(find.text('Everything is paid up'), findsNothing);
      // And the row itself says Due rather than Paid.
      expect(find.text('Due'), findsOneWidget);
    });
  });

  group('the first month', () {
    testWidgets('welcomes a new household rather than apologising', (
      tester,
    ) async {
      await _pump(
        tester,
        platform: _Platform(
          month: _month(delivered: '0.000', expected: null),
        ),
      );
      // Nothing has gone wrong. Nothing has started.
      expect(find.text('Welcome to Lacteva'), findsOneWidget);
      expect(
        find.textContaining('Once the dairy sets up your standing order'),
        findsOneWidget,
      );
      expect(
        find.textContaining('Your first delivery will appear here'),
        findsOneWidget,
      );
      expect(find.textContaining('No invoice'), findsOneWidget);
    });

    testWidgets('with nothing planned there is no vessel to fill', (
      tester,
    ) async {
      await _pump(
        tester,
        platform: _Platform(month: _month(delivered: '0.000', expected: null)),
      );
      // A vessel is a measurement and a measurement needs a scale.
      expect(_vessel(tester), isEmpty);
      // The caption claims no target either — only what arrived.
      expect(find.text('delivered this month'), findsOneWidget);
      expect(find.textContaining('delivered of'), findsNothing);
    });

    testWidgets('milk that arrived against no plan still draws no vessel', (
      tester,
    ) async {
      // The dangerous case: 54 L HAS arrived and there is nothing to be full
      // of. An empty vessel here would say "almost nothing came" and a full
      // one would say the app knows a target it does not have.
      await _pump(
        tester,
        platform: _Platform(month: _month(delivered: '54.000', expected: null)),
      );
      expect(_vessel(tester), isEmpty);
      expect(find.text('54.000 L'), findsOneWidget);
      expect(find.text('delivered this month'), findsOneWidget);
    });

    testWidgets('a month the platform will not report costs the figures only', (
      tester,
    ) async {
      // `/v1/deliveries/report` is gated on `sales.delivery.read`, which this
      // household holds — but the screen has always tolerated its absence and
      // must keep doing so.
      await _pump(tester, platform: _Platform(month: null));
      expect(find.text('Your milk, this month'), findsOneWidget);
      expect(find.text('—'), findsWidgets);
    });
  });

  group('the next delivery comes from the plan, never from a guess', () {
    testWidgets('says when, how much, and on what schedule', (tester) async {
      await _pump(
        tester,
        platform: _Platform(
          month: _month(today: '2026-08-26'),
          plans: const [
            {
              'id': 'p1',
              'active': true,
              'product': 'cow milk',
              'default_quantity': '2.0',
              'quantity_unit': 'L',
              'slot': 'morning',
              'schedule_key': 'schedule.daily',
              'next_delivery': '2026-08-27',
            },
          ],
        ),
      );
      expect(find.text('Tomorrow'), findsOneWidget);
      expect(
        find.text('2.0 L cow milk · Morning · your standing order'),
        findsOneWidget,
      );
      // The platform sends a KEY and the catalog decides the sentence.
      expect(find.text('On its way daily'), findsOneWidget);
    });

    testWidgets('an inactive plan promises nothing', (tester) async {
      await _pump(
        tester,
        platform: _Platform(
          month: _month(),
          plans: const [
            {
              'id': 'p1',
              'active': false,
              'product': 'cow milk',
              'default_quantity': '2.0',
              'quantity_unit': 'L',
              'schedule_key': 'schedule.daily',
              'next_delivery': '2026-08-27',
            },
          ],
        ),
      );
      expect(find.text('Welcome to Lacteva'), findsOneWidget);
      expect(find.text('On its way daily'), findsNothing);
    });
  });

  group('the week strip', () {
    testWidgets('fills what arrived, lights today, outlines what has not', (
      tester,
    ) async {
      await _pump(
        tester,
        platform: _Platform(
          month: _month(today: '2026-08-26'),
          deliveries: [
            _delivery('2026-08-24'),
            _delivery('2026-08-25'),
            _delivery('2026-08-26'),
          ],
        ),
      );
      expect(find.text('THIS WEEK'), findsOneWidget);
      for (final day in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']) {
        expect(find.text(day), findsOneWidget, reason: day);
      }
      // Three days carry a figure; the four still to come carry none.
      final cells = _dayCells(tester).toList();
      expect(cells.length, 7);
      expect(
        cells.where((c) => (c.properties.value ?? '').isNotEmpty).length,
        3,
      );
      // And those four are OUTLINED, not drawn as past days that stayed
      // empty — a Thursday that has not come has not been missed.
      expect(_dashedDays(tester), 4);
    });

    testWidgets('a day that was missed is not a day that has not come', (
      tester,
    ) async {
      await _pump(
        tester,
        platform: _Platform(
          month: _month(today: '2026-08-26'),
          deliveries: [
            _delivery('2026-08-24'),
            // Tuesday: recorded, but not delivered. It carries no figure and
            // is not drawn as "still to come" either.
            {
              'customer_id': 'cust-1',
              'delivery_date': '2026-08-25',
              'slot': 'morning',
              'status': 'skipped',
              'quantity': null,
              'invoice_id': null,
            },
          ],
        ),
      );
      expect(
        _dayCells(tester)
            .where((c) => (c.properties.value ?? '').isNotEmpty)
            .length,
        1,
      );
      // Tuesday was recorded and not delivered: it is empty, but it is not
      // one of the days still to come.
      expect(_dashedDays(tester), 4);
    });
  });

  group('the shimmer is the only thing that moves', () {
    testWidgets('the mark keeps a frame scheduled, and nothing else does', (
      tester,
    ) async {
      await _pump(tester, platform: _Platform(month: _month()));
      expect(tester.binding.hasScheduledFrame, isTrue);
      // It is decoration, so it is not announced.
      expect(find.byIcon(Icons.water_drop), findsOneWidget);
    });

    testWidgets('reduced motion stops it entirely, mark still drawn', (
      tester,
    ) async {
      await _pump(
        tester,
        platform: _Platform(month: _month()),
        reducedMotion: true,
      );
      // No controller at all, rather than a controller running at zero.
      expect(tester.binding.hasScheduledFrame, isFalse);
      expect(find.byIcon(Icons.water_drop), findsOneWidget);
      // And the screen is otherwise identical.
      expect(find.text('Your milk, this month'), findsOneWidget);
      expect(find.text('54.000 L'), findsOneWidget);
    });
  });

  group('read-only, and in the household own language', () {
    testWidgets('a Hindi household reads Hindi, from the same keys', (
      tester,
    ) async {
      await _pump(
        tester,
        platform: _Platform(month: _month()),
        session: _session(locale: 'hi'),
      );
      expect(find.text('इस महीने का आपका दूध'), findsOneWidget);
      expect(find.text('सब भुगतान हो चुका है'), findsOneWidget);
      expect(find.text('Your milk, this month'), findsNothing);
    });

    testWidgets('reads its own account in a fixed number of calls', (
      tester,
    ) async {
      // Six aggregates for the whole page, whatever the history holds — not
      // one request per invoice and not one per delivery (§13).
      final platform = await _pump(
        tester,
        platform: _Platform(
          month: _month(),
          deliveries: [for (var d = 1; d <= 28; d++) _delivery('2026-08-0$d')],
          invoices: const [
            {
              'id': 'i1',
              'invoice_number': 'A',
              'period_from': '2026-07-01',
              'period_to': '2026-07-31',
              'amount_due': '0.00',
              'status': 'paid',
              'line_count': 30,
            },
            {
              'id': 'i2',
              'invoice_number': 'B',
              'period_from': '2026-06-01',
              'period_to': '2026-06-30',
              'amount_due': '0.00',
              'status': 'paid',
              'line_count': 30,
            },
          ],
        ),
      );
      expect(platform.calls.length, 6);
    });
  });
}
