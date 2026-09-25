/// The household's whole bill history, a page at a time (WO-86).
///
/// What is pinned:
///
///   * the tab opens on the platform's statement — opening, billed, paid,
///     closing — with the closing figure the household actually owes;
///   * the first page is one request; "show earlier" asks the platform for
///     the NEXT page by offset rather than fetching everything and slicing,
///     and disappears when every invoice is on screen;
///   * a bill's screen lists the receipts applied to THAT bill, matched by
///     invoice number as a whole member of `applied_to` — "INV-1" does not
///     claim "INV-10", and a payment that closed two bills appears on both.
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/customer_portal.dart';
import 'package:lacteva_mobile/src/session.dart';
import 'package:lacteva_mobile/src/shell.dart';
import 'package:lacteva_mobile/src/theme.dart';
import 'responsive/matrix.dart';

Session _session() => Session(
  userId: 'u1',
  email: 'household@example.com',
  fullName: 'Deshmukh',
  tenantId: 'org-1',
  customerId: 'cust-1',
  locale: 'en',
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

Map<String, dynamic> _invoice(int n) => <String, dynamic>{
  'id': 'i$n',
  'invoice_number': 'INV-2026-${n.toString().padLeft(6, '0')}',
  'period_from': '2026-0${(n % 8) + 1}-01',
  'period_to': '2026-0${(n % 8) + 1}-28',
  'amount_due': n == 30 ? '660.00' : '0.00',
  'status': n == 30 ? 'issued' : 'paid',
  'line_count': 28,
};

class _Platform extends ApiClient {
  _Platform({this.invoices = const [], this.receipts = const []});

  final List<Map<String, dynamic>> invoices;
  final List<Map<String, dynamic>> receipts;
  final List<String> calls = [];

  @override
  Future<Map<String, dynamic>> listInvoices({
    String? customerId,
    String? status,
    int limit = 20,
    int offset = 0,
  }) async {
    calls.add('listInvoices limit=$limit offset=$offset');
    final slice = invoices.skip(offset).take(limit).toList();
    return <String, dynamic>{'items': slice, 'total': invoices.length};
  }

  @override
  Future<Map<String, dynamic>> customerStatement(
    String customerId, {
    String? dateFrom,
    String? dateTo,
  }) async {
    calls.add('customerStatement $customerId');
    return <String, dynamic>{
      'customer_id': customerId,
      'date_from': '2026-09-01',
      'date_to': '2026-09-25',
      'opening_balance': '1860.00',
      'billed': '0.00',
      'paid': '1200.00',
      'closing_balance': '660.00',
      'currency': 'INR',
      'entries': const [],
    };
  }

  @override
  Future<Map<String, dynamic>> listCustomerReceipts({
    String? customerId,
    int limit = 20,
    int offset = 0,
  }) async {
    calls.add('listCustomerReceipts');
    return <String, dynamic>{'items': receipts, 'total': receipts.length};
  }

  /// WO-83 §2: the bytes the share sheet is handed are the platform's.
  final Uint8List pdf = Uint8List.fromList('%PDF-1.4 fake'.codeUnits);
  String previousBalance = '0.00';

  @override
  Future<Uint8List> invoicePdf(String id) async {
    calls.add('invoicePdf $id');
    return pdf;
  }

  @override
  Future<Map<String, dynamic>> invoiceDetail(String id) async {
    calls.add('invoiceDetail $id');
    return <String, dynamic>{
      'invoice': {
        ..._invoice(int.parse(id.substring(1))),
        'previous_balance': previousBalance,
      },
      'lines': const [],
      'paid': '1200.00',
      'outstanding': '660.00',
      'totals_match_lines': true,
    };
  }
}

Future<void> _pump(WidgetTester tester, Widget home) async {
  tester.view.physicalSize = const Size(390, 1600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(theme: lactevaTheme(), home: home));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

void main() {
  group('the bills tab', () {
    testWidgets('opens on the statement and pages the history by offset', (
      tester,
    ) async {
      final platform = _Platform(
        invoices: [for (var n = 30; n >= 1; n--) _invoice(n)],
      );
      await _pump(
        tester,
        CustomerBillsScreen(client: platform, session: _session()),
      );

      // The statement, from the platform: what they owe is the closing figure.
      expect(find.byKey(const ValueKey('bills-statement')), findsOneWidget);
      expect(find.text('This month at a glance'), findsOneWidget);
      expect(
        tester.widget<Text>(find.byKey(const ValueKey('bills-closing'))).data,
        contains('660.00'),
      );

      // One page of 24, one request — and the button for the rest.
      expect(
        platform.calls.where((c) => c.startsWith('listInvoices')).toList(),
        ['listInvoices limit=24 offset=0'],
      );
      expect(find.byKey(const ValueKey('bill-row-i30')), findsOneWidget);
      expect(find.text('INV-2026-000030'), findsOneWidget);
      expect(find.text('That is every invoice.'), findsNothing);

      // The list builds lazily: the button is below 24 rows.
      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('bills-more')),
        400,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.byKey(const ValueKey('bills-more')), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('bills-more')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));

      expect(
        platform.calls.where((c) => c.startsWith('listInvoices')).toList(),
        ['listInvoices limit=24 offset=0', 'listInvoices limit=24 offset=24'],
      );
      await tester.scrollUntilVisible(
        find.text('That is every invoice.'),
        400,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text('That is every invoice.'), findsOneWidget);
      expect(find.byKey(const ValueKey('bills-more')), findsNothing);
    });

    testWidgets('a bill is not read from the wrong field names', (
      tester,
    ) async {
      // Before WO-86 the tab read `period_start` and `total_amount`, which the
      // platform has never sent, so every row said "→" with nothing around
      // it. The period and status are the platform's own fields now.
      final platform = _Platform(invoices: [_invoice(30)]);
      await _pump(
        tester,
        CustomerBillsScreen(client: platform, session: _session()),
      );
      expect(find.textContaining('2026-07-01 → 2026-07-28'), findsOneWidget);
      expect(find.textContaining('Due'), findsOneWidget);
      expect(find.textContaining('660.00'), findsWidgets);
    });
  });

  group('receipts against a bill', () {
    test('match by whole invoice number, never by substring', () {
      final receipts = [
        {'receipt_number': 'R-1', 'applied_to': 'INV-1'},
        {'receipt_number': 'R-2', 'applied_to': 'INV-10'},
        {'receipt_number': 'R-3', 'applied_to': 'INV-1, INV-2'},
        {'receipt_number': 'R-4', 'applied_to': ''},
      ];
      expect(
        receiptsFor(receipts, 'INV-1').map((r) => r['receipt_number']),
        ['R-1', 'R-3'],
      );
      expect(
        receiptsFor(receipts, 'INV-10').map((r) => r['receipt_number']),
        ['R-2'],
      );
      expect(receiptsFor(receipts, 'INV-2').length, 1);
      expect(receiptsFor(receipts, 'INV-9'), isEmpty);
    });

    testWidgets('the bill screen lists its own receipts and no others', (
      tester,
    ) async {
      final platform = _Platform(
        receipts: [
          {
            'id': 'rc-1',
            'receipt_number': 'RCT-2026-000009',
            'payment_number': 'PAY-2026-000009',
            'amount': '1200.00',
            'method': 'UPI',
            'applied_to': 'INV-2026-000030',
            'generated_at': '2026-09-03T10:00:00Z',
          },
          {
            'id': 'rc-2',
            'receipt_number': 'RCT-2026-000004',
            'payment_number': 'PAY-2026-000004',
            'amount': '1860.00',
            'method': 'CASH',
            'applied_to': 'INV-2026-000029, INV-2026-000028',
            'generated_at': '2026-08-03T10:00:00Z',
          },
        ],
      );
      await _pump(
        tester,
        CustomerBillScreen(
          client: platform,
          invoiceId: 'i30',
          session: _session(),
        ),
      );
      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('bill-receipts')),
        400,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text('Payments against this invoice'), findsOneWidget);
      expect(
        find.byKey(const ValueKey('bill-receipt-RCT-2026-000009')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey('bill-receipt-RCT-2026-000004')),
        findsNothing,
      );
      expect(find.textContaining('UPI'), findsOneWidget);
    });

    testWidgets('Download hands the platform PDF to the share sheet', (
      tester,
    ) async {
      final platform = _Platform();
      final shared = <(Uint8List, String)>[];
      await _pump(
        tester,
        CustomerBillScreen(
          client: platform,
          invoiceId: 'i30',
          session: _session(),
          share: (bytes, filename) async => shared.add((bytes, filename)),
        ),
      );
      await tester.tap(find.byKey(const ValueKey('bill-download')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      expect(platform.calls, contains('invoicePdf i30'));
      expect(shared, hasLength(1));
      expect(shared.single.$1, same(platform.pdf));
      expect(shared.single.$2, 'INV-2026-000030.pdf');
    });

    testWidgets('a household in credit reads Advance, not a negative debt', (
      tester,
    ) async {
      final platform = _Platform()..previousBalance = '-412.00';
      await _pump(
        tester,
        CustomerBillScreen(
          client: platform,
          invoiceId: 'i30',
          session: _session(),
        ),
      );
      expect(find.text('Advance'), findsOneWidget);
      expect(find.text('Brought forward'), findsNothing);
      expect(find.text('412.00'), findsOneWidget);
      expect(find.text('-412.00'), findsNothing);
    });

    testWidgets('says so when nothing has been paid against it', (
      tester,
    ) async {
      await _pump(
        tester,
        CustomerBillScreen(
          client: _Platform(),
          invoiceId: 'i30',
          session: _session(),
        ),
      );
      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('bill-receipts')),
        400,
        scrollable: find.byType(Scrollable).first,
      );
      expect(
        find.text('No payment has been recorded against this invoice yet.'),
        findsOneWidget,
      );
    });
  });

  group('responsive matrix (WO-96 / D-45)', () {
    testWidgets('the bills tab renders at every size and text scale', (tester) async {
      final platform = _Platform(invoices: List.generate(30, _invoice));
      await pumpMatrix(
        tester,
        'CustomerBillsScreen',
        () => CustomerBillsScreen(key: UniqueKey(), client: platform, session: _session()),
      );
    });

    testWidgets('a bill renders at every size and text scale', (tester) async {
      await pumpMatrix(
        tester,
        'CustomerBillScreen',
        () => CustomerBillScreen(
          key: UniqueKey(),
          client: _Platform(),
          invoiceId: 'i30',
          session: _session(),
        ),
      );
    });
  });
}
