/// Sync-on-resume and sync-on-sign-in (P1-MOBILE-COUNTER-001; audit D-13).
///
/// The queue used to wait for a manual tap: one transport blip at 5 a.m. and
/// every later capture silently queued all morning. What is pinned:
///   1. landing home after sign-in triggers a sync attempt — but only when
///      something is actually waiting;
///   2. returning to the app (lifecycle resume) triggers another attempt;
///   3. the trigger is fire-and-forget — a sync failure never breaks the
///      screen, the queue simply keeps the work.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/home.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';
import 'package:lacteva_mobile/src/offline/sync_engine.dart';

class _Client extends OfflineApiClient {
  _Client({required this.pending, this.syncThrows = false})
    : super(queue: SyncQueue(MemoryOfflineStore()), deviceId: 'test-device');

  final int pending;
  final bool syncThrows;
  int syncCalls = 0;

  @override
  int get pendingCount => pending;

  @override
  Future<SyncRunResult> syncNow() async {
    syncCalls++;
    if (syncThrows) throw Exception('sync died');
    return const SyncRunResult(
      applied: 0,
      duplicates: 0,
      conflicts: 0,
      failed: 0,
      batches: 0,
    );
  }

  @override
  Future<Map<String, dynamic>> me() async => {
    'id': 'u1',
    'email': 'operator@dairy.example',
    'full_name': 'Operator',
    'tenant_id': 'org-1',
    'customer_id': null,
    'permissions': ['collection.session.manage', 'collection.center.read'],
  };

  @override
  Future<CenterPage> listCenters({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) async => CenterPage(items: const [], total: 0);
}

Future<void> _pumpHome(WidgetTester tester, _Client client) async {
  await tester.pumpWidget(MaterialApp(home: HomeRouter(client: client)));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('signing in syncs the waiting queue once', (tester) async {
    final client = _Client(pending: 3);
    await _pumpHome(tester, client);
    expect(client.syncCalls, 1);
  });

  testWidgets('an empty queue triggers nothing', (tester) async {
    final client = _Client(pending: 0);
    await _pumpHome(tester, client);
    expect(client.syncCalls, 0);
  });

  testWidgets('returning to the app tries again', (tester) async {
    final client = _Client(pending: 3);
    await _pumpHome(tester, client);
    expect(client.syncCalls, 1);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(client.syncCalls, 2);
  });

  testWidgets('a sync failure never breaks the screen', (tester) async {
    final client = _Client(pending: 3, syncThrows: true);
    await _pumpHome(tester, client);
    expect(client.syncCalls, 1);
    expect(tester.takeException(), isNull, reason: 'fire-and-forget swallows');
    // The home actually rendered.
    expect(find.text('Collection centres'), findsOneWidget);
  });
}
