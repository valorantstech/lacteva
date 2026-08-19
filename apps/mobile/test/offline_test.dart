import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';
import 'package:lacteva_mobile/src/offline/sync_engine.dart';

/// A stand-in platform. Records every batch it receives and answers with
/// whatever outcome the test wants — including refusing to answer at all,
/// which is how a dead network behaves.
class _FakePlatform extends ApiClient {
  _FakePlatform({
    this.failTimes = 0,
    this.conflictKinds = const {},
    this.onBatch,
  });

  int failTimes;
  final Set<String> conflictKinds;

  /// Called with the batch number as each push arrives — the hook a test uses
  /// to interfere mid-run (cancel, drop connectivity).
  final void Function(int batchNumber)? onBatch;
  final List<List<Map<String, dynamic>>> batches = [];
  final Set<String> seenOperationIds = {};

  @override
  Future<Map<String, dynamic>> pushSyncBatch({
    required String deviceId,
    required List<Map<String, dynamic>> operations,
  }) async {
    if (failTimes > 0) {
      failTimes -= 1;
      throw const SocketException('no route to host');
    }
    batches.add(operations);
    onBatch?.call(batches.length);
    final results = <Map<String, dynamic>>[];
    for (final op in operations) {
      final id = op['operation_id'] as String;
      final kind = op['kind'] as String;
      if (seenOperationIds.contains(id)) {
        results.add({
          'operation_id': id,
          'kind': kind,
          'status': 'duplicate',
          'applied': true,
          'server_id': 'server-$id',
        });
        continue;
      }
      seenOperationIds.add(id);
      if (conflictKinds.contains(kind)) {
        results.add({
          'operation_id': id,
          'kind': kind,
          'status': 'conflict',
          'applied': false,
          'conflict': {
            'reason': 'supplier_unavailable',
            'detail': 'supplier is archived, not active',
          },
        });
        continue;
      }
      results.add({
        'operation_id': id,
        'kind': kind,
        'status': 'applied',
        'applied': true,
        'server_id': 'server-$id',
        'client_reference': op['client_reference'],
      });
    }
    return {
      'accepted': operations.length,
      'applied': results.where((r) => r['status'] == 'applied').length,
      'duplicates': results.where((r) => r['status'] == 'duplicate').length,
      'conflicts': results.where((r) => r['status'] == 'conflict').length,
      'failed': 0,
      'results': results,
      'server_time': DateTime.now().toUtc().toIso8601String(),
    };
  }
}

/// An offline client whose sync engine talks to the fake platform instead of
/// the network — the same seam a real deployment uses.
OfflineApiClient _client(
  OfflineStore store, {
  _FakePlatform? platform,
  bool offline = true,
}) {
  final queue = SyncQueue(store);
  final client = OfflineApiClient(
    queue: queue,
    deviceId: 'test-device',
    engine: SyncEngine(
      client: platform ?? _FakePlatform(),
      queue: queue,
      deviceId: 'test-device',
    ),
    forceOffline: offline,
  );
  return client;
}

/// The operator's whole flow, captured with no connectivity at all.
Future<Map<String, dynamic>> _collectOffline(OfflineApiClient client) async {
  final tx = await client.txStep(
    '/v1/milk-transactions',
    body: {'session_id': 'local-session-1'},
  );
  final id = tx['id'] as String;
  await client.txStep(
    '/v1/milk-transactions/$id/identify',
    body: {'method': 'code', 'value': 'S-000123'},
  );
  await client.txStep(
    '/v1/milk-transactions/$id/milk',
    body: {
      'milk_type': 'cow',
      'container_type': 'can',
      'container_identifier': 'C-1',
    },
  );
  await client.txStep(
    '/v1/milk-transactions/$id/weight',
    body: {'source': 'manual', 'gross': 30.0, 'tare': 5.0},
  );
  await client.txStep(
    '/v1/milk-transactions/$id/quality',
    body: {'source': 'manual', 'fat': 4.2, 'snf': 8.5, 'clr': 28.0},
  );
  await client.txStep('/v1/milk-transactions/$id/accept');
  return client.txStep('/v1/milk-transactions/$id/complete');
}

/// Real disk IO under a loaded machine: `flutter test` runs suites
/// concurrently, and the default 30-second per-test timeout is a machine-speed
/// assertion, not a correctness one — it made this file fail intermittently
/// only on slow runs (P1-LOCALE-I18N-001 housekeeping). The timeout is
/// widened, never the assertions.
const _ioTimeout = Timeout(Duration(minutes: 2));

void main() {
  test('offline, the session lookup answers empty so entry can queue (P0-PILOT-004)', () async {
    final client = OfflineApiClient(
      queue: SyncQueue(MemoryOfflineStore()),
      deviceId: 'test-device',
      forceOffline: true,
    );
    expect(await client.listOpenSessions('center-1'), isEmpty);
    final session = await client.openCollectionSession('center-1');
    expect(session['offline'], isTrue);
    expect(client.pendingCount, 1);
  }, timeout: _ioTimeout);

  // --- collecting with no network -----------------------------------------

  test('a full collection can be captured with no connectivity', () async {
    final client = _client(MemoryOfflineStore());
    final tx = await _collectOffline(client);

    expect(tx['state'], 'COMPLETED');
    expect(tx['offline'], isTrue);
    expect(tx['net_weight'], 25.0); // an echo of what was entered
    expect(tx['fat'], 4.2);
    // Pricing is the platform's decision, never the device's.
    expect(tx['pricing_status'], 'pending_sync');
    expect(tx['gross_amount'], isNull);
    expect(client.queue.operations.length, 7);
    expect(
      client.queue.operations.map((o) => o.kind),
      containsAllInOrder([
        'create_transaction',
        'identify_supplier',
        'receive_milk',
        'capture_weight',
        'capture_quality',
        'accept',
        'complete',
      ]),
    );
  }, timeout: _ioTimeout);

  test('offline operations carry unique idempotency keys', () async {
    final client = _client(MemoryOfflineStore());
    await _collectOffline(client);
    final ids = client.queue.operations.map((o) => o.operationId).toSet();
    expect(ids.length, 7);
    for (final id in ids) {
      expect(id, matches(RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-')));
    }
  }, timeout: _ioTimeout);

  test(
    'a session opened offline is referenced locally by its collection',
    () async {
      final client = _client(MemoryOfflineStore());
      final session = await client.openCollectionSession('center-1');
      expect(session['offline'], isTrue);
      final tx = await client.txStep(
        '/v1/milk-transactions',
        body: {'session_id': session['id']},
      );
      final create = client.queue.operations.last;
      expect(create.kind, 'create_transaction');
      expect(create.targetRef, session['id']);
      expect(tx['id'], startsWith('local-tx-'));
    },
    timeout: _ioTimeout,
  );

  // --- durability ----------------------------------------------------------

  test('the queue survives an app restart', () async {
    final store = MemoryOfflineStore();
    await _collectOffline(_client(store));

    // A brand-new client over the same storage: a fresh app process.
    final restarted = _client(store);
    await restarted.queue.load();
    expect(restarted.queue.operations.length, 7);
    expect(restarted.queue.operations.first.kind, 'create_transaction');
    expect(
      restarted.queue.operations.every((o) => o.state == SyncState.pending),
      isTrue,
    );
  }, timeout: _ioTimeout);

  test(
    'the queue survives on disk and tolerates a corrupt file',
    () async {
      final dir = await Directory.systemTemp.createTemp('lacteva-offline');
      final path = '${dir.path}/queue.json';
      await _collectOffline(_client(FileOfflineStore(path)));
      expect(await File(path).exists(), isTrue);

      final reopened = _client(FileOfflineStore(path));
      await reopened.queue.load();
      expect(reopened.queue.operations.length, 7);

      // A crash mid-write leaves garbage: start clean rather than crash-loop.
      await File(path).writeAsString('{not json');
      final afterCorruption = _client(FileOfflineStore(path));
      await afterCorruption.queue.load();
      expect(afterCorruption.queue.operations, isEmpty);
      await dir.delete(recursive: true);
    },
    // The ONLY test here that touches a real filesystem, and the default 30s
    // is a harness limit rather than a guarantee: under a full parallel run
    // on a loaded machine this times out while passing every time it is run
    // alone. Nothing about durability or corruption tolerance is relaxed —
    // every assertion above is unchanged — but a test that fails half the
    // full runs teaches people to ignore red, which is worse than slow.
    timeout: const Timeout(Duration(minutes: 2)),
  );

  test('a crash mid-push recovers in-flight work', () async {
    final store = MemoryOfflineStore();
    final client = _client(store);
    await _collectOffline(client);
    // Simulate a process death while the batch was in flight.
    client.queue.markSyncing(client.queue.operations.take(3));
    await client.queue.save();

    final recovered = _client(store);
    await recovered.queue.load();
    expect(
      recovered.queue.operations.where((o) => o.state == SyncState.syncing),
      isEmpty,
    );
    expect(recovered.queue.due().length, 7); // nothing stranded
  }, timeout: _ioTimeout);

  // --- synchronisation ------------------------------------------------------

  test('sync uploads everything and records the time', () async {
    final platform = _FakePlatform();
    final client = _client(MemoryOfflineStore(), platform: platform);
    await _collectOffline(client);

    final result = await client.syncNow();
    expect(result.applied, 7);
    expect(result.failed, 0);
    expect(
      client.queue.operations.every((o) => o.state == SyncState.synced),
      isTrue,
    );
    expect(client.queue.lastSyncAt, isNotNull);
    expect(platform.batches.length, 1);
  }, timeout: _ioTimeout);

  test('sync is batched', () async {
    final platform = _FakePlatform();
    final queue = SyncQueue(MemoryOfflineStore());
    final client = OfflineApiClient(
      queue: queue,
      deviceId: 'test-device',
      engine: SyncEngine(
        client: platform,
        queue: queue,
        deviceId: 'test-device',
        batchSize: 3,
      ),
      forceOffline: true,
    );
    await _collectOffline(client);
    final result = await client.syncNow();
    expect(result.applied, 7);
    expect(platform.batches.length, 3); // 3 + 3 + 1
    expect(platform.batches.first.length, 3);
  }, timeout: _ioTimeout);

  test('replaying the same operations does not duplicate them', () async {
    final platform = _FakePlatform();
    final client = _client(MemoryOfflineStore(), platform: platform);
    await _collectOffline(client);
    await client.syncNow();

    // Force a second push of the same operations (a lost acknowledgement).
    for (final op in client.queue.operations) {
      op.state = SyncState.pending;
    }
    final second = await client.syncNow();
    expect(second.duplicates, 7);
    expect(second.applied, 0);
    expect(platform.seenOperationIds.length, 7); // the server saw 7, ever
  }, timeout: _ioTimeout);

  test('network loss mid-sync loses nothing and backs off', () async {
    final platform = _FakePlatform(failTimes: 1);
    final client = _client(MemoryOfflineStore(), platform: platform);
    await _collectOffline(client);

    final failed = await client.syncNow();
    expect(failed.failed, 7);
    expect(failed.error, isNotNull);
    expect(
      client.queue.operations.every((o) => o.state == SyncState.failed),
      isTrue,
    );
    expect(client.queue.operations.first.nextAttemptAt, isNotNull);

    // Nothing is due yet — the backoff is respected.
    expect(client.queue.due(now: DateTime.now().toUtc()), isEmpty);
    // …but the operator can force it, and everything lands.
    final retried = await client.engine.retryFailed();
    expect(retried.applied, 7);
  }, timeout: _ioTimeout);

  test('partial synchronisation resumes where it stopped', () async {
    final platform = _FakePlatform();
    final queue = SyncQueue(MemoryOfflineStore());
    final client = OfflineApiClient(
      queue: queue,
      deviceId: 'test-device',
      engine: SyncEngine(
        client: platform,
        queue: queue,
        deviceId: 'test-device',
        batchSize: 3,
      ),
      forceOffline: true,
    );
    await _collectOffline(client);

    // First run dies after one batch.
    platform.failTimes = 0;
    final first = await client.engine.sync();
    expect(first.applied, 7);

    // More work captured later syncs on its own without re-sending the rest.
    await _collectOffline(client);
    final second = await client.syncNow();
    expect(second.applied, 7);
    expect(second.duplicates, 0);
  }, timeout: _ioTimeout);

  test('backoff grows with attempts and is capped', () {
    expect(SyncQueue.backoff(1), const Duration(seconds: 2));
    expect(SyncQueue.backoff(2), const Duration(seconds: 4));
    expect(SyncQueue.backoff(3), const Duration(seconds: 8));
    expect(SyncQueue.backoff(20), const Duration(seconds: 300));
  }, timeout: _ioTimeout);

  test('an exhausted operation stops retrying by itself', () async {
    final client = _client(MemoryOfflineStore());
    await _collectOffline(client);
    for (final op in client.queue.operations) {
      op.state = SyncState.failed;
      op.attempts = 5;
      op.nextAttemptAt = null;
    }
    expect(client.queue.due(), isEmpty); // maxAttempts reached
    client.queue.retryAll(); // the operator's explicit decision
    expect(client.queue.due().length, 7);
  }, timeout: _ioTimeout);

  test('cancellation stops between batches and strands nothing', () async {
    late SyncEngine engine;
    // Cancel once the first batch has landed — sync() clears stale flags on
    // entry, so cancellation only means anything DURING a run.
    final platform = _FakePlatform(
      onBatch: (n) {
        if (n == 1) engine.cancel();
      },
    );
    final queue = SyncQueue(MemoryOfflineStore());
    engine = SyncEngine(
      client: platform,
      queue: queue,
      deviceId: 'test-device',
      batchSize: 2,
    );
    final client = OfflineApiClient(
      queue: queue,
      deviceId: 'test-device',
      engine: engine,
      forceOffline: true,
    );
    await _collectOffline(client);

    final result = await engine.sync();
    expect(result.cancelled, isTrue);
    expect(result.applied, 2); // the batch already in flight was honoured
    expect(
      queue.operations.where((o) => o.state == SyncState.pending).length,
      5,
    );
    expect(
      queue.operations.where((o) => o.state == SyncState.syncing),
      isEmpty,
    );

    // Resuming completes the rest without re-sending what already landed.
    final resumed = await engine.sync();
    expect(resumed.applied, 5);
    expect(resumed.duplicates, 0);
    expect(queue.operations.every((o) => o.state == SyncState.synced), isTrue);
  }, timeout: _ioTimeout);

  // --- conflicts ------------------------------------------------------------

  test('a conflict is surfaced, never silently overwritten', () async {
    final platform = _FakePlatform(conflictKinds: {'identify_supplier'});
    final client = _client(MemoryOfflineStore(), platform: platform);
    await _collectOffline(client);

    final result = await client.syncNow();
    expect(result.conflicts, 1);
    final conflicted = client.queue.operations.firstWhere(
      (o) => o.kind == 'identify_supplier',
    );
    expect(conflicted.state, SyncState.conflict);
    expect(conflicted.conflictReason, 'supplier_unavailable');
    expect(conflicted.conflictDetail, contains('archived'));
    // A conflict is NOT retried automatically — it needs a human.
    expect(client.queue.due(), isEmpty);
  }, timeout: _ioTimeout);

  test('the id map learns local-to-server mappings as they sync', () async {
    final platform = _FakePlatform();
    final client = _client(MemoryOfflineStore(), platform: platform);
    final tx = await client.txStep(
      '/v1/milk-transactions',
      body: {'session_id': 'server-session'},
    );
    await client.syncNow();
    expect(client.queue.resolve(tx['id'] as String), isNotNull);
  }, timeout: _ioTimeout);

  // --- snapshot for the UI ---------------------------------------------------

  test('the snapshot reports what the operator needs to know', () async {
    final platform = _FakePlatform(conflictKinds: {'complete'});
    final client = _client(MemoryOfflineStore(), platform: platform);
    await _collectOffline(client);

    var snapshot = client.snapshot();
    expect(snapshot.online, isFalse);
    expect(snapshot.pending, 7);
    expect(snapshot.hasWork, isTrue);
    expect(snapshot.lastSyncAt, isNull);

    await client.syncNow();
    snapshot = client.snapshot();
    expect(snapshot.synced, 6);
    expect(snapshot.conflicts, 1);
    expect(snapshot.outstanding, 0);
    expect(snapshot.lastSyncAt, isNotNull);
  }, timeout: _ioTimeout);

  // --- business rules are the platform's, not the device's -------------------

  test(
    'a business error from the platform is not swallowed by the queue',
    () async {
      // Believed ONLINE: a 409 is an answer, not a connectivity problem, so it
      // must surface exactly as it would online rather than being queued.
      final queue = SyncQueue(MemoryOfflineStore());
      final client = _RejectingClient(queue: queue, deviceId: 'test-device');
      expect(
        () => client.txStep('/v1/milk-transactions/abc/accept'),
        throwsA(isA<ApiException>()),
      );
      await Future<void>.delayed(Duration.zero);
      expect(queue.operations, isEmpty); // nothing was queued behind the error
    },
    timeout: _ioTimeout,
  );

  test('the device never prices milk', () async {
    final client = _client(MemoryOfflineStore());
    final tx = await _collectOffline(client);
    expect(tx['gross_amount'], isNull);
    expect(tx['unit_price'], isNull);
    expect(tx['currency'], isNull);
    expect(tx['pricing_status'], 'pending_sync');
  }, timeout: _ioTimeout);
}

/// Believes it is online and always gets a business rejection.
class _RejectingClient extends OfflineApiClient {
  _RejectingClient({required super.queue, required super.deviceId})
    : super(forceOffline: false);

  @override
  Future<Map<String, dynamic>> txStep(String path, {Object? body}) async {
    if (path.endsWith('/accept')) {
      throw ApiException(409, 'transaction is not in a decidable state');
    }
    return super.txStep(path, body: body);
  }
}
