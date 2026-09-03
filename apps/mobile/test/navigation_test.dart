/// Navigation, which the app did not have (WO-72 Part B · D-23 pin 10).
///
/// Thirty-three screens were reachable and three were advertised. What is
/// pinned here:
///
///   1. every `*Screen` class in lib/src has a home under a tab — the map is
///      code, and this test walks the source so a new screen without a home
///      fails the build rather than becoming findable only by drilling;
///   2. the bar is shaped per experience exactly as the design review drew
///      it, and a tab whose every destination is forbidden does not render;
///   3. navigation is capability-driven and never role-named — the map
///      contains no role string;
///   4. the bar renders, switches, and each hub offers only what the session
///      may open.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/navigation.dart';
import 'package:lacteva_mobile/src/session.dart';
import 'package:lacteva_mobile/src/shell.dart';

Session _session(Set<String> permissions, {String? customerId}) => Session(
  userId: 'u1',
  email: 'x@example.com',
  fullName: 'X',
  tenantId: 'org-1',
  permissions: permissions,
  customerId: customerId,
);

final _manager = _session({
  'collection.session.manage',
  'sales.delivery.record',
  'supplier.read',
  'settlement.read',
  'payment.read',
  'receipt.read',
  'pricing.ratecard.read',
  'reporting.read',
  'notification.read',
  'collection.center.read',
  'collection.transaction.read',
  'operations.readiness.read',
  'operations.device.read',
});
final _operator = _session({
  'collection.session.manage',
  'collection.transaction.record',
  'collection.transaction.read',
  'supplier.read',
  'reporting.read',
});
final _driver = _session({'logistics.run.execute'});
final _salesRider = _session({'sales.delivery.record', 'sales.delivery.read'});
final _customer = _session({'sales.delivery.read'}, customerId: 'c-1');

class _Fake extends ApiClient {
  @override
  Future<CenterPage> listCenters({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) async => CenterPage.fromJson({
    'items': [
      {'id': 'c1', 'branch_id': 'b1', 'name': 'Sitara Centre', 'code': 'SIT-001', 'status': 'active'},
    ],
    'total': 1,
    'limit': limit,
    'offset': offset,
  });
}

void main() {
  group('the map is complete (pin 10)', () {
    test('every screen in lib/src has a home under a tab', () {
      final classes = <String>{};
      for (final file in Directory('lib/src').listSync(recursive: true).whereType<File>()) {
        if (!file.path.endsWith('.dart')) continue;
        for (final m in RegExp(r'class (\w+Screen) extends').allMatches(file.readAsStringSync())) {
          classes.add(m.group(1)!);
        }
      }
      expect(classes.length, greaterThanOrEqualTo(38));
      final homeless = classes.where(
        (c) => !screenHomes.containsKey(c) && !preAuthScreens.contains(c),
      );
      expect(homeless, isEmpty, reason: 'a screen with no home is findable only by drilling');
      // And nothing in the map is a screen that does not exist.
      final phantom = screenHomes.keys.where((c) => !classes.contains(c));
      expect(phantom, isEmpty);
      // Every home names a tab that shape actually has.
      for (final entry in screenHomes.entries) {
        for (final home in entry.value.entries) {
          expect(
            tabsOf(home.key).map((t) => t.key),
            contains(home.value),
            reason: '${entry.key} is homed under "${home.value}", which the ${home.key} bar lacks',
          );
        }
      }
    });

    test('the map and the hubs name no role', () {
      final source = File('lib/src/navigation.dart').readAsStringSync() +
          File('lib/src/shell.dart').readAsStringSync();
      for (final role in ['tenant-admin', 'ORGANIZATION_MANAGER', 'COLLECTION_OPERATOR', 'CENTRE_MANAGER', 'DRIVER', 'SALES_OFFICER', 'roleNames']) {
        expect(source.contains(role), isFalse, reason: 'navigation must not branch on a role name: $role');
      }
    });
  });

  group('the bar is shaped per experience and pruned by capability', () {
    test('a manager gets Today / Farmers / Money / Reports / More', () {
      expect(tabsFor(_manager).map((t) => t.key), ['today', 'farmers', 'money', 'reports', 'more']);
    });
    test('an operator gets Collect / Today / Farmers / More', () {
      expect(tabsFor(_operator).map((t) => t.key), ['collect', 'today', 'farmers', 'more']);
    });
    test('a driver gets Round / More — Deliver needs the sales grant', () {
      expect(tabsFor(_driver).map((t) => t.key), ['round', 'more']);
      expect(tabsFor(_salesRider).map((t) => t.key), ['round', 'deliver', 'more']);
    });
    test('a household gets Deliveries / Bill / More', () {
      expect(tabsFor(_customer).map((t) => t.key), ['deliveries', 'bill', 'more']);
    });
    test('a tab whose every destination is forbidden does not render', () {
      final noMoney = _session({..._manager.permissions}..removeAll(
        ['settlement.read', 'payment.read', 'receipt.read', 'pricing.ratecard.read'],
      ));
      expect(tabsFor(noMoney).map((t) => t.key), isNot(contains('money')));
      final noFarmers = _session({..._operator.permissions}..remove('supplier.read'));
      expect(tabsFor(noFarmers).map((t) => t.key), ['collect', 'today', 'more']);
    });
  });

  group('the shell', () {
    testWidgets('renders the bar and switches tabs without losing a tab', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: AppShell(
            client: _Fake(),
            session: _manager,
            roots: {
              'today': (_) => const Scaffold(body: Text('TODAY ROOT')),
              'farmers': (_) => const Scaffold(body: Text('FARMERS ROOT')),
              'money': (_) => const Scaffold(body: Text('MONEY ROOT')),
              'reports': (_) => const Scaffold(body: Text('REPORTS ROOT')),
              'more': (_) => const Scaffold(body: Text('MORE ROOT')),
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(NavigationBar), findsOneWidget);
      for (final label in ['Today', 'Farmers', 'Money', 'Reports', 'More']) {
        expect(find.text(label), findsOneWidget);
      }
      await tester.tap(find.text('Money'));
      await tester.pumpAndSettle();
      expect(find.text('MONEY ROOT'), findsOneWidget);
      await tester.tap(find.text('Today'));
      await tester.pumpAndSettle();
      // IndexedStack keeps every tab mounted: Money is still there, offstage,
      // so a half-typed search or a loaded list survives a tab switch.
      expect(find.text('TODAY ROOT'), findsOneWidget);
      expect(find.text('MONEY ROOT', skipOffstage: false), findsOneWidget);
    });

    testWidgets('a bar of one tab is no bar', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: AppShell(
            client: _Fake(),
            session: _driver,
            roots: {'round': (_) => const Scaffold(body: Text('ROUND'))},
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(NavigationBar), findsNothing);
      expect(find.text('ROUND'), findsOneWidget);
    });

    testWidgets('a hub offers only what the session may open, and says so in its language', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: HubScreen(
            client: _Fake(),
            session: _session({'settlement.read', 'pricing.ratecard.read'}),
            titleKey: 'nav.money',
            items: moneyItems,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Settlements'), findsOneWidget);
      expect(find.text('Rate cards'), findsOneWidget);
      expect(find.text('Pricing matrices'), findsOneWidget);
      expect(find.text('Test a rate'), findsOneWidget);
      // Absent, not disabled.
      expect(find.text('Payments'), findsNothing);
      expect(find.text('Receipts'), findsNothing);
    });

    testWidgets('the More hub carries sign-out', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: HubScreen(
            client: _Fake(),
            session: _operator,
            titleKey: 'nav.more',
            items: operatorMoreItems,
            signOut: true,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('hub-signOut')), findsOneWidget);
      expect(find.byKey(const ValueKey('hub-sync')), findsOneWidget);
      // Instruments needs `operations.device.read`, which this operator lacks.
      expect(find.byKey(const ValueKey('hub-instruments')), findsNothing);
    });
  });
}
