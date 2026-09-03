/// WO-72 Part C · D-23 — the manager's own screen.
///
/// The review's three rules, each asked of the widget tree: every figure is
/// comparative or actionable; every alert says what, since when and what to
/// do, with a real control; nothing is assumed — the unit comes from the
/// record, and a figure the platform did not give is said to be missing.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/centers.dart';
import 'package:lacteva_mobile/src/manager_home.dart';
import 'package:lacteva_mobile/src/session.dart';
import 'package:lacteva_mobile/src/suppliers.dart';
import 'package:lacteva_mobile/src/transactions_history.dart';

class _Dairy extends ApiClient {
  _Dairy({
    this.todayLitres = 412.5,
    this.lastWeekLitres = 380.0,
    this.lastWeekMissing = false,
    this.served = 38,
    this.activeFarmers = 52,
    this.unpriced = 0,
    this.failedChecks = 0,
    this.sessionOpen = true,
    this.byMilkType = const [
      {'milk_type': 'cow', 'transactions': 30, 'net_weight_kg': 300.0, 'quantity_unit': 'litre',
        'weighted_avg_fat': 4.1, 'amount_by_currency': {'INR': '13000.00'}},
      {'milk_type': 'buffalo', 'transactions': 10, 'net_weight_kg': 112.5, 'quantity_unit': 'litre',
        'weighted_avg_fat': 6.2, 'amount_by_currency': {'INR': '5450.00'}},
    ],
  });

  final double todayLitres;
  final double lastWeekLitres;
  final bool lastWeekMissing;
  final int served;
  final int activeFarmers;
  final int unpriced;
  final int failedChecks;
  final bool sessionOpen;
  final List<Map<String, dynamic>> byMilkType;

  final List<String> calls = [];

  /// The week before today, by day, as the platform would answer it.
  static const history = <String, double>{
    '2026-08-27': 395.0,
    '2026-08-28': 401.5,
    '2026-08-29': 388.0,
    '2026-08-30': 410.0,
    '2026-08-31': 402.0,
    '2026-09-01': 399.5,
  };

  @override
  Future<CenterPage> listCenters({String query = '', String status = '', int limit = 20, int offset = 0}) async {
    calls.add('listCenters');
    return CenterPage.fromJson({
      'items': [
        {'id': 'c0', 'branch_id': 'b1', 'name': 'Sitara Centre', 'code': 'SIT-00', 'status': 'active', 'timezone': null},
      ],
      'total': 1,
    });
  }

  @override
  Future<DailySummaryView> dailyReport(String centerId, {String? on, String? from, String? to}) async {
    calls.add('dailyReport(${on ?? (from == null ? 'today' : '$from..$to')})');
    if (on == '2026-08-26' && lastWeekMissing) throw StateError('no report');
    final litres = from != null
        ? 8_120.0 // the cycle so far
        : on == null
        ? todayLitres
        : on == '2026-08-26'
        ? lastWeekLitres
        : (history[on] ?? 0.0);
    return DailySummaryView.fromJson(<String, dynamic>{
      'date_from': from ?? on ?? '2026-09-02',
      'transactions': 41,
      'accepted': 40,
      'rejected': 1,
      'suppliers_served': on == null && from == null ? served : 40,
      'total_net_weight_kg': litres,
      'quantity_unit': 'litre',
      'payable_by_currency': from != null ? {'INR': '312450.00'} : {'INR': '18450.00'},
      'unpriced_accepted': on == null && from == null ? unpriced : 0,
      'weighted_avg_fat': 4.3,
      'weighted_avg_snf': 8.4,
      'by_milk_type': on == null && from == null ? byMilkType : const [],
    });
  }

  @override
  Future<SupplierPageResult> listSuppliers({String query = '', String? centerId, int limit = 20, int offset = 0}) async {
    calls.add('listSuppliers');
    return SupplierPageResult.fromJson({'items': const [], 'total': activeFarmers});
  }

  @override
  Future<ReadinessResultView> readiness(String centerId) async {
    calls.add('readiness');
    return ReadinessResultView.fromJson({
      'status': failedChecks == 0 ? 'ready' : 'not_ready',
      'checks': [
        {'rule': 'BR-0102 rate card published', 'severity': 'info', 'passed': true, 'detail': ''},
        for (var i = 0; i < failedChecks; i++)
          {'rule': 'BR-0110 device calibrated', 'severity': 'blocking', 'passed': false, 'detail': 'analyser SIT-A1 overdue'},
      ],
    });
  }

  @override
  Future<List<Map<String, dynamic>>> listOpenSessions(String centerId) async {
    calls.add('listOpenSessions');
    return sessionOpen ? [{'id': 's1', 'label': 'morning', 'status': 'open'}] : const [];
  }
}

Session _session(Set<String> permissions) => Session(
  userId: 'u1',
  email: 'owner@dairy.example',
  fullName: 'Sitara Owner',
  tenantId: 'org-1',
  permissions: permissions,
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

final _owner = _session({
  'collection.session.manage',
  'sales.delivery.record',
  'collection.center.read',
  'operations.readiness.read',
  'supplier.read',
  'collection.transaction.read',
  'reporting.read',
  'settlement.read',
});

Future<_Dairy> _pump(WidgetTester tester, {_Dairy? dairy}) async {
  final fake = dairy ?? _Dairy();
  await tester.pumpWidget(MaterialApp(home: ManagerHomeScreen(client: fake, session: _owner)));
  await tester.pumpAndSettle();
  return fake;
}

String _text(WidgetTester tester, Key key) => tester.widget<Text>(find.byKey(key)).data!;

void main() {
  group('whoever runs the dairy gets oversight, not the counter', () {
    test('the owner lands on the manager experience', () {
      expect(experienceFor(_owner), Experience.manager);
      expect(runsTheWholeDairy(_owner), isTrue);
    });

    testWidgets('the primary action of the counter is nowhere on it', (tester) async {
      await _pump(tester);
      expect(find.text('Collect milk'), findsNothing);
      expect(find.text('Sitara Dairy'), findsOneWidget);
      expect(find.text('Sitara Centre'), findsOneWidget);
      expect(find.text('Session open'), findsOneWidget);
    });
  });

  group('every figure is comparative or actionable', () {
    testWidgets('the hero carries its unit from the record, and what was expected', (tester) async {
      await _pump(tester);
      expect(_text(tester, const ValueKey('mgr-hero')), '412.5');
      expect(_text(tester, const ValueKey('mgr-unit')), 'L');
      // The expectation is the same weekday last week, read from the report.
      expect(_text(tester, const ValueKey('mgr-expected')), 'of ~380.0 L expected');
      expect(_text(tester, const ValueKey('mgr-delta')), '▲ 8.6% vs Wed');
      expect(find.byKey(const ValueKey('mgr-progress')), findsOneWidget);
    });

    testWidgets('a morning behind last week says so, and by how much', (tester) async {
      await _pump(tester, dairy: _Dairy(todayLitres: 342.0, lastWeekLitres: 380.0));
      expect(_text(tester, const ValueKey('mgr-delta')), '▼ 10.0% vs Wed');
    });

    testWidgets('no same-day figure means no invented expectation', (tester) async {
      await _pump(tester, dairy: _Dairy(lastWeekMissing: true));
      expect(_text(tester, const ValueKey('mgr-expected')), 'no same-day figure to compare');
      expect(find.byKey(const ValueKey('mgr-delta')), findsNothing);
      expect(find.byKey(const ValueKey('mgr-progress')), findsNothing);
      // The rest of the screen is unharmed by the one refusal.
      expect(_text(tester, const ValueKey('mgr-hero')), '412.5');
    });

    testWidgets('farmers are counted against the active roll', (tester) async {
      await _pump(tester);
      expect(find.text('38 of 52 farmers'), findsOneWidget);
      expect(find.text('14 still to come'), findsOneWidget);
    });

    testWidgets('a full roll and a closed session are said in words', (tester) async {
      await _pump(tester, dairy: _Dairy(activeFarmers: 38, sessionOpen: false));
      expect(find.text('38 of 38 farmers'), findsOneWidget);
      expect(find.text('everyone is in'), findsOneWidget);
      expect(find.text('No open session'), findsOneWidget);
      expect(find.text('Session open'), findsNothing);
    });

    testWidgets('money is on the dashboard, formatted by the platform', (tester) async {
      final dairy = await _pump(tester);
      expect(_text(tester, const ValueKey('mgr-payable-today')), '18450.00 INR');
      expect(_text(tester, const ValueKey('mgr-payable-cycle')), '312450.00 INR');
      expect(dairy.calls, contains('dailyReport(2026-09-01..2026-09-02)'));
    });

    testWidgets('milk types read their unit from their own row', (tester) async {
      await _pump(
        tester,
        dairy: _Dairy(
          byMilkType: const [
            {'milk_type': 'cow', 'transactions': 30, 'net_weight_kg': 300.0, 'quantity_unit': 'litre',
              'weighted_avg_fat': 4.1, 'amount_by_currency': {'INR': '13000.00'}},
            {'milk_type': 'buffalo', 'transactions': 10, 'net_weight_kg': 112.5, 'quantity_unit': 'kg',
              'weighted_avg_fat': 6.2, 'amount_by_currency': {'INR': '5450.00'}},
          ],
        ),
      );
      expect(find.text('300.0 L'), findsOneWidget);
      expect(find.text('112.5 kg'), findsOneWidget);
    });
  });

  group('every alert has a stripe, a cause, a time and a control', () {
    testWidgets('a quiet morning raises no alert and no empty heading', (tester) async {
      await _pump(tester, dairy: _Dairy(served: 52));
      expect(find.textContaining('NEEDS YOU'), findsNothing);
      expect(find.text('FIX'), findsNothing);
      expect(find.text('REVIEW'), findsNothing);
      expect(find.text('VIEW'), findsNothing);
    });

    testWidgets('a failed readiness check names itself and opens readiness', (tester) async {
      await _pump(tester, dairy: _Dairy(failedChecks: 1, served: 52));
      expect(find.text('NEEDS YOU — 1'), findsOneWidget);
      expect(find.text('BR-0110 device calibrated'), findsOneWidget);
      expect(find.textContaining('analyser SIT-A1 overdue · as of '), findsOneWidget);
      await tester.tap(find.text('FIX'));
      await tester.pumpAndSettle();
      expect(find.byType(ReadinessScreen), findsOneWidget);
    });

    testWidgets('unpriced milk opens the history; absent farmers open the roll', (tester) async {
      await _pump(tester, dairy: _Dairy(unpriced: 3));
      expect(find.text('NEEDS YOU — 2'), findsOneWidget);
      expect(find.text('3 collections waiting for a price'), findsOneWidget);
      expect(find.text('14 regular farmers have not arrived'), findsOneWidget);
      await tester.tap(find.text('REVIEW'));
      await tester.pumpAndSettle();
      expect(find.byType(TransactionHistoryScreen), findsOneWidget);
      await tester.pageBack();
      await tester.pumpAndSettle();
      await tester.tap(find.text('VIEW'));
      await tester.pumpAndSettle();
      expect(find.byType(SuppliersListScreen), findsOneWidget);
    });
  });

  group('the chart can be read', () {
    testWidgets('it has a value axis, a named average, day labels and a unit', (tester) async {
      await _pump(tester);
      expect(find.text('LAST 7 MORNINGS'), findsOneWidget);
      expect(_text(tester, const ValueKey('chart-max')), '412.5');
      // (395 + 401.5 + 388 + 410 + 402 + 399.5 + 412.5) / 7
      expect(_text(tester, const ValueKey('chart-avg')), 'avg 401.2');
      // Thu 27 Aug … Wed 2 Sep, as initials under the bars.
      for (final initial in ['T', 'F', 'S', 'M', 'W']) {
        expect(find.text(initial), findsWidgets);
      }
      // Each bar is announced with its day and its unit.
      final announced = tester
          .widgetList<Semantics>(find.byType(Semantics))
          .map((s) => s.properties.label)
          .whereType<String>()
          .toList();
      expect(announced, containsAll(['Thu 395.0 L', 'Wed 412.5 L']));
    });

    testWidgets('the axis text takes its colour from the theme', (tester) async {
      final fake = _Dairy();
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData(colorScheme: const ColorScheme.dark(onSurfaceVariant: Color(0xFFABCDEF))),
          home: ManagerHomeScreen(client: fake, session: _owner),
        ),
      );
      await tester.pumpAndSettle();
      final axis = tester.widget<Text>(find.byKey(const ValueKey('chart-max')));
      expect(axis.style?.color, const Color(0xFFABCDEF));
    });
  });

  group('calendar arithmetic on the platform\'s date', () {
    test('shifts across a month boundary', () {
      expect(shiftDays('2026-09-02', -7), '2026-08-26');
      expect(shiftDays('2026-03-01', -1), '2026-02-28');
      expect(shiftDays('garbage', -7), 'garbage');
    });

    test('names the weekday Monday-first', () {
      expect(weekdayOf('2026-09-02'), 2); // a Wednesday
      expect(weekdayOf('2026-08-31'), 0); // a Monday
    });
  });
}
