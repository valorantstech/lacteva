/// What the two new screens actually put in front of a person (DEMO-012 §14).
///
/// These are not "does it render" tests. Each one asserts a promise the work
/// order makes and that a plausible implementation would break:
///
///  * the app never computes a financial figure the platform already gave it
///    (§6, §11) — asserted by making the platform's answer DISAGREE with the
///    obvious local arithmetic and requiring the platform's;
///  * a screen never offers an action the platform would refuse (§5);
///  * a round of forty households is not forty round trips (§13);
///  * a missing grant narrows a screen instead of breaking it.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/customer_portal.dart';
import 'package:lacteva_mobile/src/deliveries.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';
import 'package:lacteva_mobile/src/session.dart';

/// The app's own notion of today, and deliberately the same one: **UTC**.
///
/// This helper originally used LOCAL time and the test passed for most of a
/// day, then failed after local midnight — this machine is UTC+5:30, so the
/// two dates disagree for five and a half hours out of every twenty-four. A
/// test that computes a date differently from the code under test is a test
/// that reports the timezone rather than the behaviour.
///
/// Whether UTC is the right basis for "today" on a dairy round is a real and
/// separate question — a 5 a.m. round in India falls on the previous UTC day
/// — but it is a PLATFORM decision, not one for a client to make alone. See
/// DEMO-012-FINAL.md §11.
String _today() => DateTime.now().toUtc().toIso8601String().substring(0, 10);

/// A platform that answers, counts what it was asked, and can withhold a
/// grant — which is how the app's behaviour under partial permission is
/// tested without inventing a second permission model here.
class _FakeClient extends OfflineApiClient {
  _FakeClient({
    this.customers = const [],
    this.deliveries = const [],
    this.report,
    this.balance,
    this.invoices = const [],
    this.receipts = const [],
    this.detail,
    this.customer = const {'id': 'cus-1', 'name': 'Household 1'},
    this.refuseReporting = false,
    this.refuseReceipts = false,
  }) : super(queue: SyncQueue(MemoryOfflineStore()), deviceId: 'test');

  final List<Map<String, dynamic>> customers;
  final List<Map<String, dynamic>> deliveries;
  final Map<String, dynamic>? report;
  final Map<String, dynamic>? balance;
  final List<Map<String, dynamic>> invoices;
  final List<Map<String, dynamic>> receipts;
  final Map<String, dynamic>? detail;
  final Map<String, dynamic> customer;
  final bool refuseReporting;
  final bool refuseReceipts;

  /// Every call, in order. The N+1 test reads this.
  final List<String> calls = [];

  @override
  Future<Map<String, dynamic>> listCustomers({
    String? q,
    String? status,
    int limit = 50,
    int offset = 0,
  }) async {
    calls.add('listCustomers');
    return {'items': customers, 'total': customers.length};
  }

  @override
  Future<Map<String, dynamic>> customerDetail(String id) async {
    calls.add('customerDetail');
    return {'customer': customer};
  }

  @override
  Future<Map<String, dynamic>> customerBalance(String id) async {
    calls.add('customerBalance');
    return balance ?? const {};
  }

  @override
  Future<Map<String, dynamic>> listDeliveries({
    String? customerId,
    String? dateFrom,
    String? dateTo,
    String? status,
    bool? invoiced,
    int limit = 50,
    int offset = 0,
  }) async {
    calls.add('listDeliveries');
    return {'items': deliveries, 'total': deliveries.length};
  }

  @override
  Future<Map<String, dynamic>> deliveryReport({
    String? dateFrom,
    String? dateTo,
    String? customerId,
  }) async {
    calls.add('deliveryReport');
    if (refuseReporting) {
      throw ApiException(403, 'reporting.delivery.read required');
    }
    return report ?? const {};
  }

  @override
  Future<Map<String, dynamic>> listInvoices({
    String? customerId,
    String? status,
    int limit = 50,
    int offset = 0,
  }) async {
    calls.add('listInvoices');
    return {'items': invoices, 'total': invoices.length};
  }

  @override
  Future<Map<String, dynamic>> invoiceDetail(String id) async {
    calls.add('invoiceDetail');
    return detail ?? const {};
  }

  @override
  Future<Map<String, dynamic>> listCustomerReceipts({
    String? customerId,
    int limit = 20,
    int offset = 0,
  }) async {
    calls.add('listCustomerReceipts');
    if (refuseReceipts) throw ApiException(403, 'sales.receipt.read required');
    return {'items': receipts, 'total': receipts.length};
  }
}

Session _session({Set<String> permissions = const {}, String? customerId}) =>
    Session(
      userId: 'u1',
      email: 'someone@dairy.example',
      fullName: 'Someone',
      tenantId: 'org-1',
      permissions: permissions,
      customerId: customerId,
    );

/// Pump and settle.
///
/// `reducedMotion` exists for the household home, which shimmers its mark
/// forever by design (LACTEVA-MOBILE-007) — a settle would simply time out.
/// These tests are about what the platform said, not about the animation, and
/// asking for reduced motion is how the screen is told to stand still. The
/// shimmer itself is pinned in `customer_board_test.dart`.
Future<void> _pump(
  WidgetTester tester,
  Widget screen, {
  bool reducedMotion = false,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: reducedMotion
          ? MediaQuery(
              data: const MediaQueryData(disableAnimations: true),
              child: screen,
            )
          : screen,
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group("the delivery round", () {
    testWidgets('shows who is done and who is still waiting', (tester) async {
      final client = _FakeClient(
        // The day's totals are the SERVER's aggregate (§6/§13). The numbers
        // below deliberately disagree with what the two rows would add up to:
        // whichever the screen shows is the one a rider would repeat to the
        // dairy, and it must be the platform's.
        report: const {
          'deliveries': 9,
          'customers_served': 8,
          // LACTEVA-MOBILE-006: the board's strip reports the round's SIZE and
          // what it intended to send, both of which the report has always
          // carried. Added here so the fixture is the shape
          // `/v1/deliveries/report` actually returns — and they disagree with
          // the two rows below for the same reason the rest of it does.
          'planned': 14,
          'planned_quantity': '31.000',
          'total_quantity': '21.500',
          'quantity_unit': 'L',
          'total_amount': '1290.00',
        },
        customers: [
          {'id': 'c1', 'name': 'Household One', 'code': 'H-001'},
          {'id': 'c2', 'name': 'Household Two', 'code': 'H-002'},
        ],
        deliveries: [
          {
            'customer_id': 'c1',
            'status': 'delivered',
            'quantity': '2.000',
            'quantity_unit': 'L',
          },
        ],
      );

      await _pump(
        tester,
        DeliveryRoundScreen(
          client: client,
          session: _session(
            permissions: {'sales.delivery.record', 'sales.customer.read'},
          ),
        ),
      );

      expect(find.text('Household One'), findsOneWidget);
      expect(find.text('Household Two'), findsOneWidget);
      // The one already served says so; the other says it plainly.
      expect(find.text('H-001 · delivered · 2.0 L'), findsOneWidget);
      expect(find.text('H-002 · not yet recorded'), findsOneWidget);
      // The claim is unchanged and the selector moved with the redesign: the
      // figures are the platform's aggregate for the whole day, not a sum of
      // the rows that happen to be in memory.
      expect(
        find.text('9 / 14'),
        findsOneWidget,
        reason: "the server's count",
      );
      // WO-64: one decimal, the way a dairy says a quantity.
      expect(find.text('31.0 L'), findsOneWidget);
    });

    testWidgets('a round of forty households is not forty requests', (
      tester,
    ) async {
      // §13. The obvious implementation — fetch each customer's delivery as
      // its own request — is unusable on a phone tether and is what this
      // asserts against: the count must not grow with the round.
      final client = _FakeClient(
        customers: List.generate(
          40,
          (i) => {'id': 'c$i', 'name': 'Household $i', 'code': 'H-$i'},
        ),
      );

      await _pump(
        tester,
        DeliveryRoundScreen(
          client: client,
          session: _session(permissions: {'sales.delivery.record'}),
        ),
      );

      expect(client.calls.length, 3);
      expect(client.calls.where((c) => c == 'listDeliveries').length, 1);
    });

    testWidgets('a rider without the reporting grant still gets the round', (
      tester,
    ) async {
      // The day's totals are a separate permission. Losing them must narrow
      // the screen, not break it — a 403 on a summary card is not a reason to
      // stop a person doing their job.
      final client = _FakeClient(
        customers: [
          {'id': 'c1', 'name': 'Household One', 'code': 'H-001'},
        ],
        refuseReporting: true,
      );

      await _pump(
        tester,
        DeliveryRoundScreen(
          client: client,
          session: _session(permissions: {'sales.delivery.record'}),
        ),
      );

      expect(find.text('Household One'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsNothing);
    });

    testWidgets('a read-only session is not offered a way to record', (
      tester,
    ) async {
      // §5. Frontend hiding is never the control — the platform refuses
      // `sales.delivery.record` regardless. But offering a button that leads
      // to a refusal is a promise the app cannot keep.
      final client = _FakeClient(
        customers: [
          {'id': 'c1', 'name': 'Household One', 'code': 'H-001'},
        ],
      );

      await _pump(
        tester,
        DeliveryRoundScreen(
          client: client,
          session: _session(permissions: {'sales.delivery.read'}),
        ),
      );

      expect(find.text('Household One'), findsOneWidget);
      expect(find.byIcon(Icons.chevron_right), findsNothing);
    });

    testWidgets('the round always says what is waiting on the phone', (
      tester,
    ) async {
      // §9. A rider must never have to guess whether the last twenty minutes
      // of work is on the phone or at the dairy.
      final client = _FakeClient(customers: const []);
      await _pump(
        tester,
        DeliveryRoundScreen(
          client: client,
          session: _session(permissions: {'sales.delivery.record'}),
        ),
      );
      expect(find.textContaining('No customers on this round'), findsOneWidget);
    });
  });

  group("the customer's own account", () {
    testWidgets('shows the platform\'s balance, not its own arithmetic', (
      tester,
    ) async {
      // §6/§11. The figures below DO NOT ADD UP locally on purpose: billed
      // 1200 minus paid 900 is 300, and the platform says the outstanding
      // balance is 450.00 because an adjustment it knows about and the phone
      // does not. Whichever number the app shows is the number the customer
      // believes. It must be the platform's.
      final client = _FakeClient(
        balance: {
          'outstanding': '450.00',
          'invoiced': '1200.00',
          'paid': '900.00',
          'currency': 'INR',
          'unbilled_deliveries': 0,
        },
      );

      await _pump(
        tester,
        CustomerHomeScreen(
          client: client,
          session: _session(
            permissions: {'sales.invoice.read', 'sales.delivery.read'},
            customerId: 'cus-1',
          ),
        ),
        reducedMotion: true,
      );

      expect(find.text('450.00 due'), findsOneWidget);
      expect(find.text('Invoiced 1200.00 · paid 900.00'), findsOneWidget);
      expect(
        find.textContaining('300.00'),
        findsNothing,
        reason: 'a locally recomputed balance must appear nowhere',
      );
    });

    testWidgets('reads its own account only, in a fixed number of calls', (
      tester,
    ) async {
      final client = _FakeClient(
        balance: const {'outstanding': '0.00', 'currency': 'INR'},
        invoices: List.generate(
          12,
          (i) => {
            'id': 'inv-$i',
            'invoice_number': 'INV-$i',
            'amount_due': '100.00',
            'status': 'issued',
          },
        ),
        deliveries: List.generate(
          60,
          (i) => {
            'id': 'd$i',
            'delivery_date': '2026-08-01',
            'status': 'delivered',
          },
        ),
      );

      await _pump(
        tester,
        CustomerHomeScreen(
          client: client,
          session: _session(
            permissions: {'sales.invoice.read'},
            customerId: 'cus-1',
          ),
        ),
        reducedMotion: true,
      );

      // Six aggregates for the whole page, whatever the history holds — not
      // one request per bill and not one per delivery (§13).
      expect(client.calls.length, 6);
      expect(client.calls.where((c) => c == 'invoiceDetail'), isEmpty);
    });

    testWidgets('shows the receipts the platform issued', (tester) async {
      final client = _FakeClient(
        customer: const {'id': 'cus-1', 'name': 'Nandini Household'},
        balance: const {'outstanding': '0.00', 'currency': 'INR'},
        receipts: const [
          {
            'receipt_number': 'RCT-2026-0003',
            'payment_number': 'PAY-2026-0009',
            'amount': '750.00',
            'currency': 'INR',
          },
        ],
      );

      await _pump(
        tester,
        CustomerHomeScreen(
          client: client,
          session: _session(
            permissions: {'sales.receipt.read'},
            customerId: 'cus-1',
          ),
        ),
        reducedMotion: true,
      );

      expect(find.text('RCT-2026-0003'), findsOneWidget);
      expect(find.text('750.00'), findsOneWidget);
    });

    testWidgets('a missing receipts grant hides receipts, breaks nothing', (
      tester,
    ) async {
      final client = _FakeClient(
        balance: const {'outstanding': '0.00', 'currency': 'INR'},
        refuseReceipts: true,
      );

      await _pump(
        tester,
        CustomerHomeScreen(
          client: client,
          session: _session(
            permissions: {'sales.invoice.read'},
            customerId: 'cus-1',
          ),
        ),
        reducedMotion: true,
      );

      expect(find.text('0.00 due'), findsOneWidget);
    });

    testWidgets("today's delivery is the one from today", (tester) async {
      final client = _FakeClient(
        balance: const {'outstanding': '0.00', 'currency': 'INR'},
        deliveries: [
          {
            'id': 'd1',
            'delivery_date': _today(),
            'status': 'delivered',
            'quantity': '1.500',
            'quantity_unit': 'L',
            'slot': 'morning',
          },
          {
            'id': 'd0',
            'delivery_date': '2020-01-01',
            'status': 'delivered',
            'quantity': '9.999',
            'quantity_unit': 'L',
            'slot': 'morning',
          },
        ],
      );

      await _pump(
        tester,
        CustomerHomeScreen(
          client: client,
          session: _session(
            permissions: {'sales.delivery.read'},
            customerId: 'cus-1',
          ),
        ),
        reducedMotion: true,
      );

      expect(find.textContaining('1.500'), findsWidgets);
    });
  });

  group('a bill', () {
    Map<String, dynamic> bill({required bool matches}) => {
      'invoice': {
        'invoice_number': 'INV-2026-0007',
        'period_from': '2026-07-01',
        'period_to': '2026-07-31',
        'line_count': 31,
        'subtotal': '1550.00',
        'adjustments': '-50.00',
        'previous_balance': '0.00',
        'amount_due': '1500.00',
        'currency': 'INR',
      },
      'lines': const [],
      'paid': '500.00',
      'outstanding': '1000.00',
      'totals_match_lines': matches,
    };

    testWidgets('renders the amounts the platform issued', (tester) async {
      final client = _FakeClient(detail: bill(matches: true));
      await _pump(
        tester,
        CustomerBillScreen(client: client, invoiceId: 'inv-1'),
      );

      expect(find.text('INV-2026-0007'), findsOneWidget);
      expect(find.text('1500.00 INR'), findsOneWidget);
      expect(find.text('1000.00'), findsOneWidget);
      expect(
        find.textContaining('Checked by the dairy'),
        findsOneWidget,
        reason: "the PLATFORM's verdict, not a sum performed in Dart",
      );
    });

    testWidgets('says so when the platform says the bill does not match', (
      tester,
    ) async {
      // The app must not quietly repair this by re-adding the lines. A bill
      // whose total has drifted from its deliveries is a finance problem, and
      // the person being billed is entitled to know rather than to be shown a
      // freshly computed number that agrees with nothing on file.
      final client = _FakeClient(detail: bill(matches: false));
      await _pump(
        tester,
        CustomerBillScreen(client: client, invoiceId: 'inv-1'),
      );

      expect(find.textContaining('no longer matches'), findsOneWidget);
      expect(find.text('1500.00 INR'), findsOneWidget);
    });
  });
}
