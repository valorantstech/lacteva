/// The collection home, per persona (LACTEVA-MOBILE-005; boards Main +
/// CentreManager).
///
/// Two variants of one screen, and the thing that must be true of both: the
/// way into the capture path is there and armed before any read has answered.
/// The governing rule for this cycle is *extraordinary where the eye rests,
/// invisible where the hands work* — a hero band that made an operator wait
/// for a summary before they could start the next farmer would be exactly the
/// failure it was written to prevent.
///
/// The personas below are named for readability and defined ONLY by the
/// grants they carry, copied from the platform's own registry
/// (`modules/authz/permissions.py`). Nothing in the widget asks for a role
/// name, and nothing here supplies one.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/center_summary.dart';
import 'package:lacteva_mobile/src/centers.dart';
import 'package:lacteva_mobile/src/collection_home.dart';
import 'package:lacteva_mobile/src/collection_wizard.dart';
import 'package:lacteva_mobile/src/l10n.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';
import 'package:lacteva_mobile/src/offline/sync_engine.dart';
import 'package:lacteva_mobile/src/offline/sync_screen.dart';
import 'package:lacteva_mobile/src/session.dart';
import 'package:lacteva_mobile/src/suppliers.dart';
import 'package:lacteva_mobile/src/theme.dart';
import 'package:lacteva_mobile/src/transactions_history.dart';

/// The platform, as far as this screen is concerned.
///
/// Every method answers the shape the real client returns, because the panels
/// are supposed to be reading real platform contracts — a fixture that
/// invented a field would prove the layout and nothing else.
class _Platform extends ApiClient {
  _Platform({
    this.sessionsOpen = true,
    this.recent = const [],
    this.readinessPassed = 6,
    this.readinessFailed = 0,
    this.unpriced = 0,
    this.centres = 1,
    this.panelDelay = Duration.zero,
    this.todayEmpty = false,
    this.yesterdayEmpty = false,
    this.byMilkType = const [
      {'milk_type': 'cow', 'transactions': 30, 'net_weight_kg': 300.0, 'quantity_unit': 'litre',
        'weighted_avg_fat': 4.1, 'amount_by_currency': {'INR': '13000.00'}},
      {'milk_type': 'buffalo', 'transactions': 10, 'net_weight_kg': 112.5, 'quantity_unit': 'litre',
        'weighted_avg_fat': 6.2, 'amount_by_currency': {'INR': '5450.00'}},
    ],
  });

  final bool sessionsOpen;
  final List<Map<String, dynamic>> recent;
  final int readinessPassed;
  final int readinessFailed;
  final int unpriced;
  final int centres;

  /// WO-64. Whether the centre has taken anything yet. `todayEmpty` is the
  /// 5am state this app renders every single morning; `yesterdayEmpty` is a
  /// centre that has genuinely not run.
  final bool todayEmpty;
  final bool yesterdayEmpty;

  /// WO-56. The day split by animal, as the platform reports it — empty for
  /// the test that asks what an older platform's answer looks like.
  final List<Map<String, dynamic>> byMilkType;

  /// How long the summary takes. Zero for every test but the one that has to
  /// observe the screen BEFORE its figures arrive.
  final Duration panelDelay;

  /// The centre's operating window, in the DAIRY's clock — plain local times
  /// the platform has already resolved, which is why the footer can render
  /// them verbatim.
  static const windows = <Map<String, dynamic>>[
    {'day_of_week': 0, 'opens': '05:00', 'closes': '11:00'},
  ];

  /// What the screen asked the platform for, in order — the proof that a
  /// panel is bound to a read rather than to a constant.
  final List<String> calls = [];

  @override
  Future<CenterPage> listCenters({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) async {
    calls.add('listCenters');
    return CenterPage.fromJson({
      'items': [
        for (var i = 0; i < centres; i++)
          {
            'id': 'c$i',
            'branch_id': 'b1',
            'name': i == 0 ? 'Sitara Centre' : 'Centre $i',
            'code': 'SIT-0$i',
            'status': 'active',
            'timezone': null,
          },
      ],
      'total': centres,
    });
  }

  @override
  Future<CenterDetail> centerDetail(String id) async {
    calls.add('centerDetail');
    return CenterDetail.fromJson(<String, dynamic>{
      'center': <String, dynamic>{
        'id': id,
        'branch_id': 'b1',
        'name': 'Sitara Centre',
        'code': 'SIT-00',
        'status': 'active',
        'timezone': null,
      },
      'settings': <String, dynamic>{},
      'operating_windows': windows,
      'calendar': <Map<String, dynamic>>[],
    });
  }

  @override
  Future<DailySummaryView> dailyReport(String centerId, {String? on, String? from, String? to}) async {
    // WO-64: `on` is the day the caller asked for. The home asks for
    // YESTERDAY when today is still empty, so the fake answers for a day
    // other than today or the fallback could never be exercised.
    calls.add(on == null ? 'dailyReport' : 'dailyReport($on)');
    if (panelDelay > Duration.zero) await Future<void>.delayed(panelDelay);
    final empty = on == null ? todayEmpty : yesterdayEmpty;
    return DailySummaryView.fromJson(<String, dynamic>{
      'date_from': on ?? '2026-08-27',
      'transactions': empty ? 0 : 41,
      'accepted': empty ? 0 : 40,
      'rejected': empty ? 0 : 1,
      'suppliers_served': empty ? 0 : 38,
      'total_net_weight_kg': empty ? 0.0 : 412.5,
      // D-21 / WO-70: the unit comes WITH the figure. This dairy is a litre
      // one, and the screen must say so because the platform did — not
      // because a phone in India assumed it.
      'quantity_unit': 'litre',
      'payable_by_currency': empty ? <String, dynamic>{} : {'INR': '18450.00'},
      'unpriced_accepted': unpriced,
      'weighted_avg_fat': empty ? null : 4.3,
      'weighted_avg_snf': empty ? null : 8.4,
      // WO-56: the same litres, split by animal. The parts sum to the whole.
      'by_milk_type': empty ? const [] : byMilkType,
    });
  }

  @override
  Future<List<Map<String, dynamic>>> listOpenSessions(String centerId) async {
    calls.add('listOpenSessions');
    return sessionsOpen
        ? [
            {'id': 'sess-1', 'label': 'morning', 'status': 'open'},
          ]
        : const [];
  }

  @override
  Future<Map<String, dynamic>> openCollectionSession(String centerId) async {
    calls.add('openCollectionSession');
    return {'id': 'sess-new', 'label': 'mobile', 'status': 'open'};
  }

  @override
  Future<Map<String, dynamic>> listMilkTransactions({
    required String centerId,
    int limit = 20,
    int offset = 0,
  }) async {
    calls.add('listMilkTransactions');
    return {'items': recent, 'total': recent.length};
  }

  @override
  Future<ReadinessResultView> readiness(String centerId) async {
    calls.add('readiness');
    return ReadinessResultView.fromJson({
      'status': readinessFailed == 0 ? 'ready' : 'not_ready',
      'checks': [
        for (var i = 0; i < readinessPassed; i++)
          {
            'rule': 'rule_$i',
            'severity': 'blocking',
            'passed': true,
            'detail': '',
          },
        for (var i = 0; i < readinessFailed; i++)
          {
            'rule': 'active_scale',
            'severity': 'blocking',
            'passed': false,
            'detail': 'no active scale is assigned to this centre',
          },
      ],
    });
  }

  @override
  Future<RateCardPageResult> listRateCards({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) async {
    calls.add('listRateCards');
    return RateCardPageResult.fromJson({
      'items': [
        {
          'id': 'rc1',
          'code': 'RC-4',
          'name': 'Monsoon',
          'description': '',
          'currency': 'INR',
          'effective_from': '2026-08-25',
          'effective_until': null,
          'status': 'published',
          'version': 4,
        },
      ],
      'total': 1,
    });
  }
}

/// A client whose OWN reads go to the fake platform.
///
/// `OfflineApiClient` overrides only the handful of methods it queues; every
/// other read falls through to `ApiClient`, which would try the network. This
/// subclass sends them to the fake instead, which is what makes the widget's
/// real call graph observable.
class _OfflineFake extends OfflineApiClient {
  _OfflineFake(this.platform, SyncQueue queue)
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
  Future<CenterPage> listCenters({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) => platform.listCenters(
    query: query,
    status: status,
    limit: limit,
    offset: offset,
  );

  @override
  Future<CenterDetail> centerDetail(String id) => platform.centerDetail(id);

  @override
  Future<DailySummaryView> dailyReport(String id, {String? on, String? from, String? to}) =>
      platform.dailyReport(id, on: on);

  @override
  Future<List<Map<String, dynamic>>> listOpenSessions(String centerId) =>
      platform.listOpenSessions(centerId);

  @override
  Future<Map<String, dynamic>> openCollectionSession(String centerId) =>
      platform.openCollectionSession(centerId);

  @override
  Future<Map<String, dynamic>> listMilkTransactions({
    required String centerId,
    int limit = 20,
    int offset = 0,
  }) => platform.listMilkTransactions(
    centerId: centerId,
    limit: limit,
    offset: offset,
  );

  @override
  Future<ReadinessResultView> readiness(String centerId) =>
      platform.readiness(centerId);

  @override
  Future<RateCardPageResult> listRateCards({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) => platform.listRateCards(
    query: query,
    status: status,
    limit: limit,
    offset: offset,
  );
}

Session _session(Set<String> permissions, {String locale = 'en'}) => Session(
  userId: 'u1',
  email: 'ramesh@dairy.example',
  fullName: 'Ramesh Patil',
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

/// COLLECTION_OPERATOR's real grants. No `reporting.read`, which is the whole
/// point: the manager panels are made of that grant.
final _operator = _session({
  'collection.center.read',
  'operations.readiness.read',
  'supplier.read',
  'collection.session.manage',
  'collection.transaction.record',
  'collection.transaction.read',
});

/// CENTRE_MANAGER's real grants — the operator's, plus the three that make
/// the manager board possible.
final _manager = _session({
  'collection.center.read',
  'operations.device.read',
  'operations.readiness.read',
  'supplier.read',
  'collection.session.manage',
  'collection.transaction.read',
  'collection.transaction.record',
  'reporting.read',
  'settlement.read',
});

Future<_Platform> _pump(
  WidgetTester tester,
  Session session, {
  _Platform? platform,
  int hour = 8,
}) async {
  final fake = platform ?? _Platform();
  final queue = SyncQueue(MemoryOfflineStore());
  await tester.pumpWidget(
    MaterialApp(
      theme: lactevaTheme(),
      home: CollectionHomeScreen(
        key: UniqueKey(),
        client: _OfflineFake(fake, queue),
        session: session,
        hourOfDay: hour,
      ),
    ),
  );
  await tester.pumpAndSettle();
  return fake;
}

void main() {
  group('the greeting', () {
    test('follows the handset clock, not the business day', () {
      // The one place this app reads the phone's hour, and the comment on the
      // function says why. A business date still comes from the platform.
      expect(greetingKeyForHour(5), 'home.greetingMorning');
      expect(greetingKeyForHour(11), 'home.greetingMorning');
      expect(greetingKeyForHour(12), 'home.greetingAfternoon');
      expect(greetingKeyForHour(16), 'home.greetingAfternoon');
      expect(greetingKeyForHour(17), 'home.greetingEvening');
      expect(greetingKeyForHour(23), 'home.greetingEvening');
    });
  });

  group('the operator board', () {
    testWidgets('opens on the centre, the shift and today', (tester) async {
      await _pump(tester, _operator);

      // The hero, in board order: greeting with the person's own name, the
      // centre, and whether the shift is open.
      expect(find.text('Good morning, Ramesh'), findsOneWidget);
      expect(find.text('Sitara Centre'), findsOneWidget);
      expect(find.text('Session open'), findsOneWidget);

      // Three figures, each the platform's own — 412.5 is not arithmetic this
      // screen performed. WO-64: each now carries its unit, because a number
      // without one is a number a person has to guess at.
      expect(find.text('412.5 L'), findsOneWidget);
      expect(find.text('collected today'), findsOneWidget);
      expect(find.text('38'), findsOneWidget);
      expect(find.text('4.3%'), findsOneWidget);
    });

    testWidgets('names every door, where an icon strip named none', (
      tester,
    ) async {
      await _pump(tester, _operator);
      for (final label in [
        'Collect milk',
        "Today's collections",
        'Farmers',
        'Sync',
        'Shift history',
      ]) {
        expect(find.text(label), findsOneWidget, reason: label);
      }
      // The queue's own count, not a guess: nothing has been captured.
      expect(find.text('All sent'), findsOneWidget);
    });

    testWidgets('says the shift is closed when no session is open', (
      tester,
    ) async {
      await _pump(tester, _operator, platform: _Platform(sessionsOpen: false));
      expect(find.text('No open session'), findsOneWidget);
      expect(find.text('Session open'), findsNothing);
    });

    testWidgets('shows the last collection, and says so when there is none', (
      tester,
    ) async {
      await _pump(tester, _operator);
      expect(find.text('LAST COLLECTION'), findsOneWidget);
      expect(
        find.text('Nothing collected here yet today'),
        findsOneWidget,
      );

      await _pump(
        tester,
        _operator,
        platform: _Platform(
          recent: const [
            {
              'id': 'tx1',
              'slip_number': 'S-88A723',
              'net_weight': '12.5',
              'weight_unit': 'litre',
              'fat_percentage': '4.2',
              'gross_amount': '581.25',
              'state': 'COMPLETED',
            },
          ],
        ),
      );
      expect(find.text('S-88A723'), findsOneWidget);
      // The platform's exact decimal strings, never reformatted here.
      expect(find.textContaining('12.5 L · FAT'), findsOneWidget);
      expect(find.textContaining('581.25'), findsOneWidget);
    });

    testWidgets('closes with the shift, the centre and its code', (
      tester,
    ) async {
      await _pump(tester, _operator);
      // The window is the DAIRY's clock — plain local times the platform
      // already resolved. The open session's UTC instant is deliberately not
      // rendered as a wall clock.
      // WO-72 Part A: as a person says it — never `05:00:00 – 11:00:00`.
      expect(find.textContaining('5 am – 11 am'), findsOneWidget);
      expect(find.textContaining(':00'), findsNothing);
      expect(find.textContaining('SIT-00'), findsOneWidget);
    });

    testWidgets('shows no manager panel it could not open', (tester) async {
      final fake = await _pump(tester, _operator);
      expect(find.text('THIS MORNING'), findsNothing);
      expect(find.text('NEEDS A LOOK'), findsNothing);
      expect(find.text("Today's summary"), findsNothing);
      // And never asked for them: an operator holds no `reporting.read`, and
      // a screen that requested it would collect a 403 for nothing.
      expect(fake.calls, isNot(contains('readiness')));
      expect(fake.calls, isNot(contains('listRateCards')));
    });
  });

  group('the manager board', () {
    testWidgets('leads with readiness, the morning and what needs a look', (
      tester,
    ) async {
      await _pump(tester, _manager);
      expect(find.text('Ready 6/6'), findsOneWidget);
      expect(find.text('THIS MORNING'), findsOneWidget);
      expect(find.text('412.5'), findsOneWidget);
      // WO-72 Part A (pin 1): the unit sits against the number, read from
      // the report — this fixture's is litres.
      expect(find.text('L'), findsOneWidget);
      expect(find.text('38 farmers served'), findsOneWidget);
      // WO-56: the total, split by the animal that brought it.
      expect(find.text('cow 300.0 L · buffalo 112.5 L'), findsOneWidget);
      // WO-72 Part A (pin 8): nothing needs a look, so the section is ABSENT
      // — not a full-width card saying so.
      expect(find.text('NEEDS A LOOK'), findsNothing);
      expect(find.text('Nothing needs a look right now'), findsNothing);
      // The organization, not a role name — the house rule forbids printing
      // one as firmly as it forbids branching on one.
      expect(find.text('Sitara Dairy'), findsOneWidget);
    });

    testWidgets('invents no split when the platform reported none', (
      tester,
    ) async {
      // An older platform answers without `by_milk_type`, which is not the
      // same as a dairy taking one kind of milk. The line is absent, and no
      // zero stands in for it.
      await _pump(tester, _manager, platform: _Platform(byMilkType: const []));
      expect(find.text('412.5'), findsOneWidget);
      expect(find.textContaining('kg'), findsNothing);
    });

    testWidgets('the manager grid opens what a manager can actually open', (
      tester,
    ) async {
      await _pump(tester, _manager);
      expect(find.text('Collect milk'), findsOneWidget);
      expect(find.text("Today's summary"), findsOneWidget);
      expect(find.text('Centre calendar'), findsOneWidget);
    });

    testWidgets('needs-a-look carries real platform findings', (tester) async {
      await _pump(
        tester,
        _manager,
        platform: _Platform(
          readinessPassed: 5,
          readinessFailed: 1,
          unpriced: 3,
        ),
      );
      // Not "ready 6/6" any more, and the reason is the platform's own.
      expect(find.text('Not ready'), findsOneWidget);
      expect(
        find.text('3 collections are waiting for a price'),
        findsOneWidget,
      );
      expect(
        find.text('no active scale is assigned to this centre'),
        findsOneWidget,
      );
    });

    testWidgets('the dashboard no longer carries the rate-card footer', (
      tester,
    ) async {
      // WO-72 Part A (pin 9): the line was orphaned grey text at the foot,
      // attached to nothing and dated over a year back. A rate card is
      // something a manager ACTS on and lives on the Rate cards screen; the
      // dashboard neither asks for it nor prints it — with or without the
      // pricing grant.
      final fake = await _pump(tester, _manager);
      expect(fake.calls, isNot(contains('listRateCards')));
      final withPricing = await _pump(
        tester,
        _session({..._manager.permissions, 'pricing.ratecard.read'}),
      );
      expect(withPricing.calls, isNot(contains('listRateCards')));
      expect(find.textContaining('Rate card v'), findsNothing);
      // The foot says where you are instead.
      expect(find.textContaining('SIT-00'), findsOneWidget);
    });

    testWidgets('offers a centre switcher only when there is one to switch to', (
      tester,
    ) async {
      await _pump(tester, _manager, platform: _Platform(centres: 1));
      expect(find.byIcon(Icons.expand_more), findsNothing);

      await _pump(tester, _manager, platform: _Platform(centres: 3));
      expect(find.byIcon(Icons.expand_more), findsOneWidget);
      await tester.tap(find.text('Sitara Centre'));
      await tester.pumpAndSettle();
      // The existing list, unchanged — the home routes to it, it was not
      // rebuilt.
      expect(find.byType(CentersListScreen), findsOneWidget);
    });
  });

  group('routing — every door opens an existing screen', () {
    Future<void> tapAndExpect(
      WidgetTester tester,
      String label,
      Type screen,
    ) async {
      await _pump(tester, _operator);
      await tester.tap(find.text(label));
      await tester.pumpAndSettle();
      expect(find.byType(screen), findsOneWidget, reason: label);
    }

    testWidgets("Today's collections opens the collection history", (
      tester,
    ) async {
      await tapAndExpect(
        tester,
        "Today's collections",
        TransactionHistoryScreen,
      );
    });

    testWidgets('Farmers opens the suppliers list', (tester) async {
      await tapAndExpect(tester, 'Farmers', SuppliersListScreen);
    });

    testWidgets('Sync opens the sync status screen', (tester) async {
      await tapAndExpect(tester, 'Sync', SyncStatusScreen);
    });

    testWidgets('Shift history opens the centre screen', (tester) async {
      await tapAndExpect(tester, 'Shift history', CenterDetailScreen);
    });

    testWidgets("Today's summary opens the daily summary", (tester) async {
      await _pump(tester, _manager);
      await tester.tap(find.text("Today's summary"));
      await tester.pumpAndSettle();
      expect(find.byType(CenterTodayScreen), findsOneWidget);
    });

    testWidgets('Collect milk reuses the open session and opens the wizard', (
      tester,
    ) async {
      final fake = _Platform();
      final queue = SyncQueue(MemoryOfflineStore());
      await tester.pumpWidget(
        MaterialApp(
          theme: lactevaTheme(),
          home: CollectionHomeScreen(
            client: _OfflineFake(fake, queue),
            session: _operator,
            hourOfDay: 8,
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Collect milk'));
      await tester.pumpAndSettle();
      expect(find.byType(CollectionWizardScreen), findsOneWidget);
      // Reused, not opened again: a second session per tap would be a new
      // shift every time an operator pressed the only button on the screen.
      expect(fake.calls, isNot(contains('openCollectionSession')));
    });
  });

  group('the governing rule', () {
    testWidgets('Collect is on screen and armed before any panel answers', (
      tester,
    ) async {
      // *Invisible where the hands work.* The hero, the metrics and the
      // summary may all still be in flight; the way into the capture path may
      // not wait for them. This pumps ONE frame past the centre resolving and
      // asserts the card is already there and already tappable.
      // The summary is made slow on purpose: without it the fake wins the
      // race every time and the test would assert nothing.
      final fake = _Platform(panelDelay: const Duration(seconds: 2));
      final queue = SyncQueue(MemoryOfflineStore());
      await tester.pumpWidget(
        MaterialApp(
          theme: lactevaTheme(),
          home: CollectionHomeScreen(
            client: _OfflineFake(fake, queue),
            session: _operator,
            hourOfDay: 8,
          ),
        ),
      );
      // Let the centre resolve, and nothing else.
      await tester.pump();
      await tester.pump();

      expect(find.text('Collect milk'), findsOneWidget);
      // Still loading — the figures have not arrived, and the card is there
      // anyway.
      expect(find.text('412.5'), findsNothing);

      await tester.tap(find.text('Collect milk'));
      await tester.pumpAndSettle();
      expect(find.byType(CollectionWizardScreen), findsOneWidget);

      // Drain the slow panel so the test does not end with a pending timer.
      await tester.pump(const Duration(seconds: 3));
      await tester.pumpAndSettle();
    });

    testWidgets('nothing on this screen animates', (tester) async {
      // A frame that keeps scheduling frames is an animation. After the reads
      // settle, this screen must be completely still — no shimmer, no
      // entrance, nothing between a thumb and the next farmer.
      await _pump(tester, _operator);
      expect(tester.binding.hasScheduledFrame, isFalse);
    });
  });

  group('capability, never a role name', () {
    testWidgets('the variant follows the grant that its panels are made of', (
      tester,
    ) async {
      // The same person, the same role row, one grant apart.
      await _pump(tester, _operator);
      expect(find.text('THIS MORNING'), findsNothing);

      await _pump(
        tester,
        _session({..._operator.permissions, 'reporting.read'}),
      );
      expect(find.text('THIS MORNING'), findsOneWidget);
    });

    testWidgets('a role named anything at all changes nothing', (
      tester,
    ) async {
      // DEMO-008 made roles editable rows. A dairy that renames
      // CENTRE_MANAGER, or invents a role doing the same job, must get the
      // same screen — because the screen never asked.
      final renamed = Session(
        userId: 'u2',
        email: 'someone@dairy.example',
        fullName: 'Someone Else',
        tenantId: 'org-1',
        permissions: _manager.permissions,
        roleNames: const ['KENDRA_PRABANDHAK'],
        organization: _manager.organization,
      );
      await _pump(tester, renamed);
      expect(find.text('THIS MORNING'), findsOneWidget);
      expect(find.textContaining('KENDRA_PRABANDHAK'), findsNothing);
    });

    testWidgets('a login covering no centre is told so, not shown a wall', (
      tester,
    ) async {
      await _pump(tester, _operator, platform: _Platform(centres: 0));
      expect(find.text('No centre to open'), findsOneWidget);
      expect(find.text('Collect milk'), findsNothing);
    });
  });

  group('the words come from the catalog', () {
    testWidgets('a Hindi operator reads Hindi, from the same keys', (
      tester,
    ) async {
      await _pump(
        tester,
        _session(_operator.permissions, locale: 'hi'),
      );
      expect(find.text('दूध लें'), findsOneWidget);
      expect(find.text('किसान'), findsWidgets);
      expect(find.text('शिफ्ट चालू है'), findsOneWidget);
      // And no English left behind on the screen a Hindi operator uses most.
      expect(find.text('Collect milk'), findsNothing);
    });

    test('every key this screen looks up exists in all three catalogs', () {
      // The mirror of the parity suite, narrowed to this work order: a key
      // added to English alone renders English to a Hindi operator, which is
      // the "catalog without callers" defect wearing the other face.
      final en = catalogs['en']!;
      final mine = en.keys.where(
        (k) => k.startsWith('home.') || k.startsWith('manager.'),
      );
      expect(mine, isNotEmpty);
      for (final key in mine) {
        for (final language in ['hi', 'ar']) {
          expect(
            catalogs[language]!.containsKey(key),
            isTrue,
            reason: '$key is missing from $language',
          );
        }
      }
    });
  });

  // ===================================================================
  // WO-64 — never three em-dashes
  // ===================================================================

  group('an empty morning says something true', () {
    testWidgets('before the first collection it shows YESTERDAY, labelled', (
      tester,
    ) async {
      // This is 5am every day and the start of every demonstration. The board
      // used to render "—", "—", "—": a screen saying nothing three times,
      // which reads as broken rather than as early.
      final fake = await _pump(
        tester,
        _operator,
        platform: _Platform(todayEmpty: true),
      );
      expect(find.text('—'), findsNothing);
      expect(find.text('412.5 L'), findsOneWidget);
      expect(find.text('yesterday'), findsOneWidget);
      expect(find.text('farmers yesterday'), findsOneWidget);
      // And it ASKED for yesterday, rather than relabelling today's zero.
      expect(fake.calls.where((c) => c.startsWith('dailyReport(')), isNotEmpty);
    });

    testWidgets('an ordinary morning asks for today and nothing else', (
      tester,
    ) async {
      // The extra request exists only for the empty case; a dairy already
      // collecting must not pay for it.
      final fake = await _pump(tester, _operator);
      expect(fake.calls.where((c) => c.startsWith('dailyReport(')), isEmpty);
      expect(find.text('412.5 L'), findsOneWidget);
      expect(find.text('yesterday'), findsNothing);
    });

    testWidgets('a centre that has not run yet gets one honest line', (
      tester,
    ) async {
      // Nothing today, nothing yesterday. A zero here would claim the day had
      // been measured and found empty; this says what is actually true.
      await _pump(
        tester,
        _operator,
        platform: _Platform(todayEmpty: true, yesterdayEmpty: true),
      );
      expect(find.text('—'), findsNothing);
      expect(
        find.text('Shift open · first collection not yet taken'),
        findsOneWidget,
      );
    });

    testWidgets('with no shift open it says that instead', (tester) async {
      await _pump(
        tester,
        _operator,
        platform: _Platform(
          todayEmpty: true,
          yesterdayEmpty: true,
          sessionsOpen: false,
        ),
      );
      expect(
        find.text('No shift open yet · today has not started'),
        findsOneWidget,
      );
    });

    testWidgets('the honest line replaces the figures, never joins them', (
      tester,
    ) async {
      // A sentence explaining an absence UNDER three dashes explains it twice.
      await _pump(
        tester,
        _operator,
        platform: _Platform(todayEmpty: true, yesterdayEmpty: true),
      );
      expect(find.text('collected today'), findsNothing);
      expect(find.text('yesterday'), findsNothing);
    });
  });
}
