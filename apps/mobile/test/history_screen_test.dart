/// The centre's collection history on the phone (P1-MOBILE-COUNTER-001).
///
/// The audit found no way to answer a farmer's "you wrote 12.5 kg, not 15"
/// at the counter. What is pinned:
///   1. the list asks the platform for THIS centre only — the request carries
///      the centre id, and the platform (RLS + centre scope) decides what
///      exists; nothing here widens that;
///   2. rows show what an operator needs (slip number, when, state, kg,
///      amount) without inventing fields;
///   3. loading, empty, error+retry and honest pagination all exist;
///   4. a completed row's detail fetches the platform's own parchi.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/transactions_history.dart';

Map<String, dynamic> _tx(int n) => {
  'id': 'tx-$n',
  'state': 'COMPLETED',
  'milk_type': 'buffalo',
  'net_weight': 10 + n,
  'gross_amount': '4${n}0.00',
  'currency': 'INR',
  'slip_number': 'SLP-2026-${n.toString().padLeft(6, "0")}',
  'rejected_reason': null,
  'created_at': '2026-08-19T06:${n.toString().padLeft(2, "0")}:00+00:00',
  'fat_percentage': 6.5,
  'snf_percentage': 9.0,
  'clr_value': 28,
};

class _Fake extends ApiClient {
  _Fake({this.total = 3, this.failFirst = false});

  final int total;
  bool failFirst;
  final List<({String centerId, int limit, int offset})> calls = [];
  int slipFetches = 0;

  @override
  Future<Map<String, dynamic>> listMilkTransactions({
    required String centerId,
    int limit = 20,
    int offset = 0,
  }) async {
    calls.add((centerId: centerId, limit: limit, offset: offset));
    if (failFirst) {
      failFirst = false;
      throw const SocketException('no route to host');
    }
    final items = [
      for (var i = offset + 1; i <= (offset + limit).clamp(0, total); i++)
        _tx(i),
    ];
    return {'items': items, 'total': total, 'limit': limit, 'offset': offset};
  }

  @override
  Future<Map<String, dynamic>> transactionSlip(String txId) async {
    slipFetches++;
    return {
      'slip_number': 'SLP-2026-000001',
      'transaction_id': txId,
      'text': 'Anand Dairy\nSlip: SLP-2026-000001\nFarmer: SUP-001 · Ram Kumar',
    };
  }
}

Future<void> _pump(WidgetTester tester, _Fake client) async {
  await tester.pumpWidget(
    MaterialApp(
      home: TransactionHistoryScreen(
        // A fresh key per pump: two same-typed screens in one test must not
        // share their State (initState would be skipped for the second).
        key: UniqueKey(),
        client: client,
        centerId: 'c1',
        centerName: 'Village Centre',
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('asks the platform for this centre only, and shows the rows', (
    tester,
  ) async {
    final client = _Fake();
    await _pump(tester, client);

    expect(client.calls.single.centerId, 'c1');
    expect(find.text('SLP-2026-000001'), findsOneWidget);
    expect(find.textContaining('buffalo'), findsWidgets);
    expect(find.text('420.00 INR'), findsOneWidget);
  });

  testWidgets('empty and error states are honest, and retry recovers', (
    tester,
  ) async {
    final empty = _Fake(total: 0);
    await _pump(tester, empty);
    expect(
      find.text('No collections recorded at this centre yet.'),
      findsOneWidget,
    );

    final flaky = _Fake(failFirst: true);
    await _pump(tester, flaky);
    expect(find.text('Could not reach the platform'), findsOneWidget);
    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();
    expect(find.text('SLP-2026-000001'), findsOneWidget);
  });

  testWidgets('pagination is honest and reaches the tail', (tester) async {
    final client = _Fake(total: 25);
    await _pump(tester, client);

    // The button lives at the tail of a lazy list — scroll it into being.
    await tester.scrollUntilVisible(
      find.text('Load more (20 of 25)'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Load more (20 of 25)'));
    await tester.pumpAndSettle();
    expect(client.calls.last.offset, 20);
    await tester.scrollUntilVisible(
      find.text('SLP-2026-000025'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('SLP-2026-000025'), findsOneWidget);
    expect(find.textContaining('Load more'), findsNothing);
  });

  testWidgets('a completed row opens its detail with the platform’s parchi', (
    tester,
  ) async {
    final client = _Fake();
    await _pump(tester, client);

    await tester.tap(find.text('SLP-2026-000001'));
    await tester.pumpAndSettle();

    expect(client.slipFetches, 1);
    expect(find.text('Parchi SLP-2026-000001'), findsOneWidget);
    expect(find.textContaining('Ram Kumar'), findsOneWidget);
    expect(find.text('Copy parchi text'), findsOneWidget);
  });
}
