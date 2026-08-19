/// Expired-token replay must never strand captured work (P0-PRODUCT-008 D-3,
/// fixed in P0-PRODUCT-009).
///
/// Before the fix, the delivery and run-outcome drains treated EVERY 4xx
/// except 409 as a terminal conflict — so a token that expired while the
/// phone was offline parked a whole morning of captured deliveries as
/// "resolve with your supervisor" and never retried them, even after
/// re-authentication. What is pinned here:
///
/// 1. A 401 during replay leaves the operation QUEUED and retryable — never
///    a conflict — and stops the drain (every later operation would meet the
///    same 401).
/// 2. After re-authentication the same operations replay successfully, each
///    carrying its ORIGINAL idempotency key, exactly once.
/// 3. A 403 stays what it always was: a considered refusal (conflict) — the
///    fix must not soften genuine authorization boundaries.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';

/// The platform, unpluggable and with a revocable session.
class _FakePlatform {
  bool offline = false;
  int? refuseStatus;
  int attempts = 0;
  final List<String> keys = [];
  final List<Map<String, dynamic>> recorded = [];

  Future<dynamic> sendIdempotent(
    String method,
    String path, {
    required String idempotencyKey,
    Object? body,
  }) async {
    attempts++;
    if (refuseStatus != null) {
      throw ApiException(refuseStatus!, 'refused ($refuseStatus)');
    }
    keys.add(idempotencyKey);
    final already = keys.where((k) => k == idempotencyKey).length > 1;
    if (!already) recorded.add((body as Map).cast<String, dynamic>());
    return {'id': 'srv-${recorded.length}', 'status': 'delivered'};
  }
}

class _TestOfflineClient extends OfflineApiClient {
  _TestOfflineClient(this.platform)
    : super(
        queue: SyncQueue(MemoryOfflineStore()),
        deviceId: 'test-device',
        forceOffline: true,
      );

  final _FakePlatform platform;

  @override
  Future<dynamic> sendIdempotent(
    String method,
    String path, {
    required String idempotencyKey,
    Object? body,
  }) => platform.sendIdempotent(
    method,
    path,
    idempotencyKey: idempotencyKey,
    body: body,
  );

  @override
  Future<Map<String, dynamic>> pushSyncBatch({
    required String deviceId,
    required List<Map<String, dynamic>> operations,
  }) async => {'results': []};

  /// Make everything queued due NOW — the backoff is real time (2s floor)
  /// and a test does not sleep through it.
  void eraseBackoff() {
    for (final op in queue.due(
      now: DateTime.now().toUtc().add(const Duration(minutes: 10)),
    )) {
      op.nextAttemptAt = null;
    }
  }
}

Future<_TestOfflineClient> _withCapturedRound(_FakePlatform platform) async {
  final client = _TestOfflineClient(platform);
  for (final name in ['cus-1', 'cus-2', 'cus-3']) {
    await client.recordDeliveryOffline(
      customerId: name,
      deliveryDate: '2026-08-19',
      slot: 'morning',
      status: 'delivered',
    );
  }
  expect(client.pendingCount, 3);
  client.forceOffline = false;
  return client;
}

void main() {
  test('a 401 replay keeps the work queued and stops the drain', () async {
    final platform = _FakePlatform()..refuseStatus = 401;
    final client = await _withCapturedRound(platform);

    final run = await client.syncNow();

    expect(run.applied, 0);
    // The drain stopped on the first 401 instead of hammering the rest.
    expect(platform.attempts, 1);
    // Nothing became a conflict — a dead token is not a refusal of the milk.
    final snapshot = client.queue.snapshot(online: true, running: false);
    expect(snapshot.conflicts, 0);
    // Everything is still there to send.
    expect(client.pendingCount, greaterThanOrEqualTo(1));
  });

  test('after re-authentication the same work replays exactly once', () async {
    final platform = _FakePlatform()..refuseStatus = 401;
    final client = await _withCapturedRound(platform);
    await client.syncNow();

    // The operator signs in again; the session works.
    platform.refuseStatus = null;
    client.eraseBackoff();
    final run = await client.syncNow();

    expect(run.applied, 3);
    expect(platform.recorded.length, 3, reason: 'each delivery exactly once');
    expect(
      platform.recorded.map((r) => r['customer_id']),
      containsAll(['cus-1', 'cus-2', 'cus-3']),
    );
    expect(client.pendingCount, 0);
    // The original idempotency keys travelled on the retry.
    expect(platform.keys.toSet().length, 3);
  });

  test('a 403 is still a considered refusal — conflict, no retry', () async {
    final platform = _FakePlatform()..refuseStatus = 403;
    final client = await _withCapturedRound(platform);

    await client.syncNow();
    final snapshot = client.queue.snapshot(online: true, running: false);
    expect(snapshot.conflicts, 3, reason: 'authorization boundaries hold');

    // And a later sync does not resurrect them.
    platform.refuseStatus = null;
    client.eraseBackoff();
    final again = await client.syncNow();
    expect(again.applied, 0);
    expect(platform.recorded, isEmpty);
  });

  test('run outcomes follow the same 401 rule as deliveries', () async {
    final platform = _FakePlatform()..refuseStatus = 401;
    final client = _TestOfflineClient(platform);
    await client.recordRunOutcomeOffline(
      runId: 'run-1',
      customerId: 'cus-1',
      status: 'delivered',
    );
    expect(client.pendingCount, 1);
    client.forceOffline = false;

    await client.syncNow();
    var snapshot = client.queue.snapshot(online: true, running: false);
    expect(snapshot.conflicts, 0);

    platform.refuseStatus = null;
    client.eraseBackoff();
    final run = await client.syncNow();
    expect(run.applied, 1);
    snapshot = client.queue.snapshot(online: true, running: false);
    expect(snapshot.conflicts, 0);
    expect(client.pendingCount, 0);
  });
}
