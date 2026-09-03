/// The roundsman board (LACTEVA-MOBILE-006; board: Roundsman.dc.html).
///
/// The round is worked at a gate, one-handed, and the common case is that the
/// household takes exactly what the plan says. So the fast path is one tap on
/// DELIVERED and the stepper is the exception — which is also why the stepper
/// starts on the STANDING ORDER and shows no number.
///
/// That last point is the one this file exists to defend. The app has never
/// known a household's plan: an empty quantity is the platform's contract for
/// "whatever the plan says", and the board's tidy `2.0 L` would have been the
/// phone guessing at somebody's order. A test that let the stepper start at a
/// number would let that guess back in.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/deliveries.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';
import 'package:lacteva_mobile/src/offline/sync_engine.dart';
import 'package:lacteva_mobile/src/session.dart';
import 'package:lacteva_mobile/src/theme.dart';

class _Platform extends ApiClient {
  _Platform({
    this.report,
    this.customers = const [],
    this.deliveries = const [],
  });

  final Map<String, dynamic>? report;
  final List<Map<String, dynamic>> customers;
  final List<Map<String, dynamic>> deliveries;

  /// Exactly what the screen asked the platform to record.
  final List<String> recorded = [];

  @override
  Future<Map<String, dynamic>> deliveryReport({
    String? dateFrom,
    String? dateTo,
    String? customerId,
  }) async {
    final r = report;
    if (r == null) throw ApiException(403, 'no reporting grant');
    return r;
  }

  @override
  Future<Map<String, dynamic>> listCustomers({
    String? q,
    String? status,
    int limit = 20,
    int offset = 0,
  }) async => <String, dynamic>{
    'items': customers,
    'total': customers.length,
  };

  @override
  Future<Map<String, dynamic>> listDeliveries({
    String? customerId,
    String? dateFrom,
    String? dateTo,
    String? status,
    bool? invoiced,
    int limit = 20,
    int offset = 0,
  }) async => <String, dynamic>{
    'items': deliveries,
    'total': deliveries.length,
  };

  @override
  Future<List<Map<String, dynamic>>> listDeliveryRuns() async => const [];

  @override
  Future<Map<String, dynamic>> recordDelivery({
    required String customerId,
    required String deliveryDate,
    required String slot,
    required String status,
    String? quantity,
    String? notes,
    String? idempotencyKey,
  }) async {
    recorded.add('$customerId:$status:${quantity ?? ""}');
    return {'id': 'd-new', 'status': status};
  }
}

/// The real offline client over the fake platform, so a recorded delivery
/// travels the seam it travels in the field.
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
  Future<Map<String, dynamic>> deliveryReport({
    String? dateFrom,
    String? dateTo,
    String? customerId,
  }) => platform.deliveryReport(
    dateFrom: dateFrom,
    dateTo: dateTo,
    customerId: customerId,
  );

  @override
  Future<Map<String, dynamic>> listCustomers({
    String? q,
    String? status,
    int limit = 20,
    int offset = 0,
  }) => platform.listCustomers(
    q: q,
    status: status,
    limit: limit,
    offset: offset,
  );

  @override
  Future<Map<String, dynamic>> listDeliveries({
    String? customerId,
    String? dateFrom,
    String? dateTo,
    String? status,
    bool? invoiced,
    int limit = 20,
    int offset = 0,
  }) => platform.listDeliveries(
    customerId: customerId,
    dateFrom: dateFrom,
    dateTo: dateTo,
    status: status,
    invoiced: invoiced,
    limit: limit,
    offset: offset,
  );

  @override
  Future<List<Map<String, dynamic>>> listDeliveryRuns() =>
      platform.listDeliveryRuns();

  @override
  Future<Map<String, dynamic>> recordDelivery({
    required String customerId,
    required String deliveryDate,
    required String slot,
    required String status,
    String? quantity,
    String? notes,
    String? idempotencyKey,
  }) => platform.recordDelivery(
    customerId: customerId,
    deliveryDate: deliveryDate,
    slot: slot,
    status: status,
    quantity: quantity,
    notes: notes,
    idempotencyKey: idempotencyKey,
  );
}

Session _session({
  Set<String> permissions = const {
    'sales.delivery.record',
    'sales.customer.read',
    'reporting.read',
  },
  String locale = 'en',
}) => Session(
  userId: 'u1',
  email: 'rider@dairy.example',
  fullName: 'Rider',
  tenantId: 'org-1',
  permissions: permissions,
  locale: locale,
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

/// The day's aggregate as `/v1/deliveries/report` sends it.
const _report = <String, dynamic>{
  'date_from': '2026-08-27',
  'date_to': '2026-08-27',
  'deliveries': 9,
  'customers_served': 8,
  'planned': 14,
  'planned_quantity': '126.000',
  'total_quantity': '84.500',
  'quantity_unit': 'L',
  'total_amount': '2140.00',
};

Future<_Platform> _pump(
  WidgetTester tester, {
  Map<String, dynamic>? report = _report,
  List<Map<String, dynamic>> customers = const [],
  List<Map<String, dynamic>> deliveries = const [],
  Session? session,
  Size size = const Size(390, 844),
}) async {
  final platform = _Platform(
    report: report,
    customers: customers,
    deliveries: deliveries,
  );
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: lactevaTheme(),
      home: DeliveryRoundScreen(
        key: UniqueKey(),
        client: _Client(platform, SyncQueue(MemoryOfflineStore())),
        session: session ?? _session(),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return platform;
}

const _joshi = {'id': 'c1', 'name': 'Joshi household', 'code': 'H-001'};
const _patil = {'id': 'c2', 'name': 'Patil household', 'code': 'H-002'};
const _cafe = {'id': 'c3', 'name': 'Café Madhuban', 'code': 'H-003'};
const _tea = {'id': 'c4', 'name': 'Shree Tea House', 'code': 'H-004'};

void main() {
  group('the round header and its figures', () {
    testWidgets('says the day, the size of the round and where it came from', (
      tester,
    ) async {
      await _pump(tester, customers: const [_joshi, _patil]);
      expect(find.text("Today's round"), findsOneWidget);
      // The date is the PLATFORM's, rendered verbatim. A phone cannot turn an
      // ISO date into the dairy's "Wed 27 Aug" without a timezone database.
      expect(find.textContaining('2026-08-27'), findsOneWidget);
      expect(find.textContaining('2 customers'), findsOneWidget);
      expect(find.textContaining('from standing orders'), findsOneWidget);
    });

    testWidgets('shows the platform aggregate, never local arithmetic', (
      tester,
    ) async {
      // The fixture's totals deliberately disagree with what the two rows
      // below would add up to. Whichever number the screen shows is the one a
      // rider repeats to the dairy, and it must be the platform's.
      await _pump(tester, customers: const [_joshi, _patil]);
      // WO-64: one decimal, because that is how a dairy says a quantity —
      // the platform still stores and sends three.
      expect(find.text('126.0 L'), findsOneWidget);
      expect(find.text('to deliver'), findsOneWidget);
      expect(find.text('9 / 14'), findsOneWidget);
      expect(find.text('done'), findsOneWidget);
      // WO-64: and money wears its currency. "2140.00" alone is a number,
      // not an amount — the WO-61 defect in a smaller font.
      expect(find.text('2140.00'), findsNothing);
      expect(find.text('₹2140.00'), findsOneWidget);
    });

    testWidgets('a rider without the reporting grant still gets the round', (
      tester,
    ) async {
      // Reporting is its own grant. Losing it costs the figures, not the work.
      await _pump(tester, report: null, customers: const [_joshi]);
      expect(find.text('Joshi household'), findsOneWidget);
      expect(find.text('to deliver'), findsNothing);
      expect(find.byType(CircularProgressIndicator), findsNothing);
    });

    testWidgets('claims no money it cannot see', (tester) async {
      // The board's third figure was cash collected at the door. Nothing links
      // a customer payment to a round or a day, so the strip shows the day's
      // delivered VALUE — which the report does compute — and says so.
      await _pump(tester, customers: const [_joshi]);
      expect(find.textContaining('collected at door'), findsNothing);
      expect(find.text('value'), findsOneWidget);
    });
  });

  group('the pending card', () {
    testWidgets('starts on the standing order, showing no invented number', (
      tester,
    ) async {
      await _pump(tester, customers: const [_joshi]);
      expect(find.text('Joshi household'), findsOneWidget);
      // WO-64: "Not yet" rather than "Pending", and quiet rather than amber —
      // a stop nobody has reached is the expected state of a round that has
      // just started, not a warning.
      expect(find.text('Not yet'), findsOneWidget);
      expect(find.text('Standing order'), findsOneWidget);
      // Not 2.0 L, not 0.0 L, and not any other number the app would have had
      // to make up. The one litre figure on screen is the platform's own
      // day-total in the strip above — the card contributes none.
      expect(find.textContaining(' L'), findsOneWidget);
      expect(find.text('126.0 L'), findsOneWidget);
    });

    testWidgets('one tap sends the plan, with no quantity at all', (
      tester,
    ) async {
      final platform = await _pump(tester, customers: const [_joshi]);
      await tester.tap(find.text('Delivered'));
      await tester.pumpAndSettle();
      // An EMPTY quantity is the platform's contract for "whatever the plan
      // says". Sending a number here would override a household's order with
      // the app's guess.
      expect(platform.recorded, ['c1:delivered:']);
    });

    testWidgets('the stepper overrides only when the rider moves it', (
      tester,
    ) async {
      final platform = await _pump(tester, customers: const [_joshi]);
      await tester.tap(find.bySemanticsLabel('More'));
      await tester.pump();
      expect(find.text('0.5 L'), findsOneWidget);
      await tester.tap(find.bySemanticsLabel('More'));
      await tester.pump();
      expect(find.text('1.0 L'), findsOneWidget);

      await tester.tap(find.text('Delivered'));
      await tester.pumpAndSettle();
      expect(platform.recorded, ['c1:delivered:1.0']);
    });

    testWidgets('stepping back down hands the decision to the plan again', (
      tester,
    ) async {
      // Zero is not a quantity — a delivery of nothing is a skipped delivery,
      // which is a different outcome with a different word. So the bottom of
      // the stepper is the standing order, not 0.
      final platform = await _pump(tester, customers: const [_joshi]);
      await tester.tap(find.bySemanticsLabel('More'));
      await tester.pump();
      await tester.tap(find.bySemanticsLabel('Less'));
      await tester.pump();
      expect(find.text('Standing order'), findsOneWidget);
      expect(find.text('0.0 L'), findsNothing);

      await tester.tap(find.text('Delivered'));
      await tester.pumpAndSettle();
      expect(platform.recorded, ['c1:delivered:']);
    });

    testWidgets('a read-only session gets no way to record', (tester) async {
      // Frontend hiding is never the control — the platform refuses
      // `sales.delivery.record` regardless. But offering a button that leads
      // to a refusal is a promise the app cannot keep.
      await _pump(
        tester,
        customers: const [_joshi],
        session: _session(
          permissions: {'sales.delivery.read', 'sales.customer.read'},
        ),
      );
      expect(find.text('Joshi household'), findsOneWidget);
      expect(find.text('Delivered'), findsNothing);
      expect(find.bySemanticsLabel('More'), findsNothing);
    });
  });

  group('the outcome chips', () {
    testWidgets('a delivered row already invoiced says so', (tester) async {
      await _pump(
        tester,
        customers: const [_cafe],
        deliveries: const [
          {
            'customer_id': 'c3',
            'status': 'delivered',
            'quantity': '20.000',
            'quantity_unit': 'L',
            'amount': '1120.00',
            'invoice_id': 'inv-1',
          },
        ],
      );
      expect(find.text('On invoice'), findsOneWidget);
      expect(find.textContaining('20.0 L'), findsOneWidget);
    });

    testWidgets('a delivered row not yet invoiced shows what it is worth', (
      tester,
    ) async {
      // The board said "₹84 taken". Nothing links a customer payment to a
      // delivery, so claiming money changed hands would be the app inventing a
      // receipt. What IS true is the platform's own amount, still to be
      // invoiced — and the ₹ comes from the organization, not from a country
      // this app believes it is in.
      await _pump(
        tester,
        customers: const [_patil],
        deliveries: const [
          {
            'customer_id': 'c2',
            'status': 'delivered',
            'quantity': '1.500',
            'quantity_unit': 'L',
            'amount': '84.00',
            'invoice_id': null,
          },
        ],
      );
      expect(find.text('₹84.00 to invoice'), findsOneWidget);
      expect(find.textContaining('taken'), findsNothing);
    });

    testWidgets('a missed row says to come back', (tester) async {
      await _pump(
        tester,
        customers: const [_tea],
        deliveries: const [
          {
            'customer_id': 'c4',
            'status': 'skipped',
            'quantity': null,
            'invoice_id': null,
          },
        ],
      );
      // WO-64: the outcome names itself AND what follows from it. "Retry
      // later" said neither — and wore the same amber as a stop nobody had
      // reached yet, so a failure and a wait read as siblings.
      expect(find.text('Skipped'), findsOneWidget);
      expect(find.text('Retry later'), findsNothing);
      // The status arrives as a CODE and the catalog decides the word, and
      // the CONSEQUENCE rides on the detail line where there is width for it.
      expect(find.textContaining('not delivered'), findsOneWidget);
      expect(find.textContaining('not invoiced'), findsOneWidget);
    });

    testWidgets('a missed row in Hindi reads Hindi, from the same keys', (
      tester,
    ) async {
      await _pump(
        tester,
        customers: const [_tea],
        deliveries: const [
          {'customer_id': 'c4', 'status': 'skipped', 'invoice_id': null},
        ],
        session: _session(locale: 'hi'),
      );
      expect(find.text('छोड़ा'), findsOneWidget);
      expect(find.text('Skipped'), findsNothing);
      expect(find.textContaining('बिल नहीं'), findsOneWidget);
    });
  });

  group('what the redesign did not touch', () {
    testWidgets('the empty round is still told plainly', (tester) async {
      await _pump(tester, customers: const []);
      expect(find.textContaining('No customers on this round'), findsOneWidget);
    });

    testWidgets('the round always says what is waiting on the phone', (
      tester,
    ) async {
      await _pump(tester, customers: const [_joshi]);
      expect(find.text('All deliveries sent'), findsOneWidget);
    });

    testWidgets('a full row still opens the detail screen', (tester) async {
      // The card's Delivered is the fast path; the slot, the returned outcome
      // and a note still live behind the row, untouched.
      await _pump(tester, customers: const [_joshi]);
      await tester.tap(find.text('Joshi household'));
      await tester.pumpAndSettle();
      expect(find.byType(RecordDeliveryScreen), findsOneWidget);
    });

    testWidgets('long names on a 320px phone do not overflow', (tester) async {
      await _pump(
        tester,
        size: const Size(320, 568),
        customers: const [
          {
            'id': 'c9',
            'name': 'M/s Lakshminarayana Provisions & General Stores Pvt Ltd',
            'code': 'H-009',
          },
        ],
      );
      expect(find.textContaining('Lakshminarayana'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group('nothing on the action path animates', () {
    testWidgets('the board is still once it has loaded', (tester) async {
      await _pump(tester, customers: const [_joshi]);
      expect(tester.binding.hasScheduledFrame, isFalse);
    });
  });


  // ===================================================================
  // WO-64 — the round reads as work, not as a list
  // ===================================================================

  group('the round is grouped by what has to be done', () {
    test('a stop with no outcome is work; a delivery is done; anything else needs a look', () {
      // A pure function, so the ordering rule is testable without a phone —
      // the same reason `inRouteOrder` is public.
      final groups = groupRound(
        const [
          {'id': 'c1', 'name': 'Nobody has been'},
          {'id': 'c2', 'name': 'Delivered'},
          {'id': 'c3', 'name': 'Came back'},
          {'id': 'c4', 'name': 'Skipped'},
        ],
        const {
          'c2': {'status': 'delivered'},
          'c3': {'status': 'returned'},
          'c4': {'status': 'skipped'},
        },
      );
      expect(groups.toDeliver.map((c) => c['id']), ['c1']);
      expect(groups.delivered.map((c) => c['id']), ['c2']);
      // Both non-delivery outcomes are the part of the round somebody has to
      // decide about, and they come first for that reason.
      expect(groups.attention.map((c) => c['id']), ['c3', 'c4']);
    });

    test('route order survives inside a group — the sequence is the road', () {
      final groups = groupRound(
        const [
          {'id': 'c1'},
          {'id': 'c2'},
          {'id': 'c3'},
        ],
        const {},
      );
      // Reordering within "to deliver" would send a van back on itself.
      expect(groups.toDeliver.map((c) => c['id']), ['c1', 'c2', 'c3']);
    });

    test('progress is the platform\'s rows counted, and absent when there is no round', () {
      expect(
        groupRound(const [
          {'id': 'a'},
          {'id': 'b'},
        ], const {
          'a': {'status': 'delivered'},
        }).progress,
        0.5,
      );
      // A bar at 0% on an empty round would report a failure that is an
      // absence.
      expect(groupRound(const [], const {}).progress, isNull);
    });

    testWidgets('the screen shows the groups, and the progress as a bar', (
      tester,
    ) async {
      await _pump(
        tester,
        customers: const [_joshi, _patil, _tea],
        deliveries: const [
          {'customer_id': 'c2', 'status': 'delivered', 'quantity': '2.000'},
          {'customer_id': 'c4', 'status': 'skipped'},
        ],
        // Tall enough that all three groups are laid out at once: a ListView
        // gives no element to a child below the fold, so a shorter surface
        // would test scrolling rather than grouping. The 320px fit is its own
        // test, above.
        size: const Size(390, 1600),
      );
      expect(find.text('NEEDS ATTENTION'), findsOneWidget);
      expect(find.text('TO DELIVER'), findsOneWidget);
      expect(find.text('DELIVERED'), findsOneWidget);
      // "0 / 14" was the whole answer before. The bar is the feeling and the
      // sentence is the count; a roundsman asks both.
      expect(find.byType(LinearProgressIndicator), findsOneWidget);
      expect(find.textContaining('of 3 delivered'), findsOneWidget);
    });

    testWidgets('an empty group is not a heading over nothing', (tester) async {
      await _pump(tester, customers: const [_joshi]);
      expect(find.text('TO DELIVER'), findsOneWidget);
      expect(find.text('NEEDS ATTENTION'), findsNothing);
      expect(find.text('DELIVERED'), findsNothing);
    });
  });

  group('a failure does not look like a wait', () {
    Color? chipGround(WidgetTester tester, String text) {
      final chip = tester.widget<Container>(
        find
            .ancestor(of: find.text(text), matching: find.byType(Container))
            .first,
      );
      return (chip.decoration as BoxDecoration?)?.color;
    }

    testWidgets('a stop nobody has reached is quiet, not amber', (tester) async {
      await _pump(tester, customers: const [_joshi]);
      expect(chipGround(tester, 'Not yet'), LactevaColors.neutralTint);
    });

    testWidgets('milk that came back gets the only danger ground on the screen', (
      tester,
    ) async {
      await _pump(
        tester,
        customers: const [_tea],
        deliveries: const [
          {'customer_id': 'c4', 'status': 'returned', 'invoice_id': null},
        ],
        size: const Size(390, 1200),
      );
      expect(find.text('Returned'), findsOneWidget);
      expect(find.textContaining('not invoiced'), findsOneWidget);
      expect(chipGround(tester, 'Returned'), LactevaColors.dangerTint);
    });

    testWidgets('a skip is amber — something happened, nothing is owed', (
      tester,
    ) async {
      await _pump(
        tester,
        customers: const [_tea],
        deliveries: const [
          {'customer_id': 'c4', 'status': 'skipped', 'invoice_id': null},
        ],
      );
      expect(chipGround(tester, 'Skipped'), LactevaColors.warningTint);
    });

    testWidgets('a correction is quiet: nothing to chase', (tester) async {
      await _pump(
        tester,
        customers: const [_tea],
        deliveries: const [
          {'customer_id': 'c4', 'status': 'cancelled', 'invoice_id': null},
        ],
      );
      expect(find.text('Cancelled'), findsOneWidget);
      expect(find.textContaining('recorded in error'), findsOneWidget);
      expect(chipGround(tester, 'Cancelled'), LactevaColors.neutralTint);
    });

    testWidgets('the two states no longer share a ground', (tester) async {
      // The defect in one assertion: "Pending" and "Retry later" were the same
      // amber, so the eye learned to skim both.
      await _pump(
        tester,
        customers: const [_joshi, _tea],
        deliveries: const [
          {'customer_id': 'c4', 'status': 'returned', 'invoice_id': null},
        ],
        size: const Size(390, 1200),
      );
      expect(
        chipGround(tester, 'Not yet'),
        isNot(chipGround(tester, 'Returned')),
      );
    });
  });
}
