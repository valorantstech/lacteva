/// Restart while offline, and the road back (P1-MOBILE-COUNTER-001 §5–§6).
///
/// The scenario the audit demanded proof for: an operator captures a full
/// collection with no signal, the app dies, the phone STAYS offline — and the
/// morning's work must still be there, visible, and must reach the platform
/// exactly once when signal and a session return. What is pinned:
///
///   1. the durable queue survives a process restart byte-for-byte — same
///      operations, same operation ids, no duplicates;
///   2. still-offline sync attempts submit nothing and lose nothing;
///   3. back online with a valid session, every operation applies EXACTLY
///      once, under its ORIGINAL id, and a second sync sends nothing;
///   4. an EXPIRED session during replay strands nothing (the P0-PRODUCT-009
///      rule) — after "sign-in" the same work applies once;
///   5. a considered business rejection becomes an inspectable conflict with
///      the platform's reason preserved — and is never retried blindly;
///   6. a transport failure stays retryable;
///   7. (the sign-in banner that SHOWS this state lives in
///      offline_banner_test.dart — widget tests must not share a file with
///      real file IO: the widget binding makes real-IO tests time out
///      intermittently under load.)
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';

/// The platform at the other end of `pushSyncBatch`, with a pluggable mood.
class _Platform {
  String mode = 'ok'; // ok | offline | expired | conflict | flaky
  final List<String> appliedIds = [];
  int batches = 0;

  Map<String, dynamic> handle(List<Map<String, dynamic>> operations) {
    batches++;
    switch (mode) {
      case 'offline':
      case 'flaky':
        throw const SocketException('no route to host');
      case 'expired':
        throw ApiException(401, 'Not authenticated');
      case 'conflict':
        return {
          'results': [
            for (final op in operations)
              {
                'operation_id': op['operation_id'],
                'status': 'conflict',
                'conflict': {
                  'reason': 'center_closed',
                  'detail': 'The centre was closed for the business date',
                },
              },
          ],
        };
      default:
        return {
          'results': [
            for (final op in operations)
              {
                'operation_id': (() {
                  appliedIds.add(op['operation_id'] as String);
                  return op['operation_id'];
                })(),
                'status': 'applied',
                'server_id': 'srv-${appliedIds.length}',
              },
          ],
        };
    }
  }
}

class _Client extends OfflineApiClient {
  _Client(String path, this.platform)
    : super(
        queue: SyncQueue(FileOfflineStore(path)),
        deviceId: 'test-device',
        forceOffline: true,
      );

  final _Platform platform;

  @override
  Future<Map<String, dynamic>> pushSyncBatch({
    required String deviceId,
    required List<Map<String, dynamic>> operations,
  }) async => platform.handle(operations);

  void eraseBackoff() {
    for (final op in queue.due(
      now: DateTime.now().toUtc().add(const Duration(minutes: 10)),
    )) {
      op.nextAttemptAt = null;
    }
  }
}


/// One full collection, captured with no signal.
Future<void> _captureOffline(OfflineApiClient client) async {
  final tx = await client.txStep(
    '/v1/milk-transactions',
    body: {'session_id': 'ses-1'},
  );
  final id = tx['id'];
  await client.txStep(
    '/v1/milk-transactions/$id/identify',
    body: {'method': 'code', 'value': 'SUP-001'},
  );
  await client.txStep(
    '/v1/milk-transactions/$id/milk',
    body: {'milk_type': 'buffalo', 'container_type': 'can'},
  );
  await client.txStep(
    '/v1/milk-transactions/$id/weight',
    body: {'source': 'manual', 'gross': 12.0, 'tare': 2.0},
  );
  await client.txStep(
    '/v1/milk-transactions/$id/quality',
    body: {'source': 'manual', 'fat': 6.5, 'snf': 9.0, 'clr': 28.0},
  );
  await client.txStep('/v1/milk-transactions/$id/accept');
  await client.txStep('/v1/milk-transactions/$id/complete');
}

/// Real file IO happens only in plain `test`s — `testWidgets` runs under
/// FakeAsync, where a real disk read never completes.
Future<(Directory, String)> _tempQueue() async {
  final dir = await Directory.systemTemp.createTemp('lacteva-restart-test');
  return (dir, '${dir.path}/queue.json');
}

/// Real disk IO under a loaded machine: `flutter test` runs suites
/// concurrently, and the default 30-second per-test timeout is a machine-speed
/// assertion, not a correctness one — it made this file fail intermittently
/// only on slow runs (P1-LOCALE-I18N-001 housekeeping). The timeout is
/// widened, never the assertions.
const _ioTimeout = Timeout(Duration(minutes: 2));

void main() {

  test('the queue survives restart byte-for-byte, then applies exactly once', () async {
    final (dir, path) = await _tempQueue();
    addTearDown(() => dir.delete(recursive: true));
    final platform = _Platform();
    // Capture with no signal, note what was queued.
    final before = _Client(path, platform);
    await _captureOffline(before);
    await before.queue.load();
    final idsBefore = [for (final op in before.queue.operations) op.operationId];
    expect(idsBefore, hasLength(7));
    expect(before.pendingCount, greaterThan(0));

    // The app dies. The phone stays offline. A NEW process opens the file.
    final after = _Client(path, platform);
    await after.queue.load();
    final idsAfter = [for (final op in after.queue.operations) op.operationId];
    expect(idsAfter, idsBefore, reason: 'same work, same ids, no duplicates');
    expect(after.pendingCount, before.pendingCount);

    // Still offline: a sync attempt submits nothing and loses nothing.
    platform.mode = 'offline';
    after.forceOffline = false;
    await after.syncNow();
    expect(platform.appliedIds, isEmpty);
    await after.queue.load();
    expect(after.queue.operations, hasLength(7));

    // Signal returns; the session is valid. Everything applies exactly once,
    // under the ORIGINAL ids captured before the restart.
    platform.mode = 'ok';
    after.eraseBackoff();
    final run = await after.syncNow();
    expect(run.applied, 7);
    expect(platform.appliedIds.toSet(), idsBefore.toSet());

    // A second sync — the duplicate-retry attempt — sends nothing.
    final again = await after.syncNow();
    expect(again.applied, 0);
    expect(platform.batches, 2);
  }, timeout: _ioTimeout);

  test('an expired session after restart strands nothing; sign-in replays once', () async {
    final (dir, path) = await _tempQueue();
    addTearDown(() => dir.delete(recursive: true));
    final platform = _Platform();
    final before = _Client(path, platform);
    await _captureOffline(before);

    final after = _Client(path, platform);
    await after.queue.load();
    after.forceOffline = false;

    // The token died while the phone was in a drawer: 401 on replay.
    platform.mode = 'expired';
    await after.syncNow();
    final snap = after.queue.snapshot(online: true, running: false);
    expect(snap.conflicts, 0, reason: 'a dead token is not a refusal');
    await after.queue.load();
    expect(after.queue.operations, hasLength(7), reason: 'nothing discarded');

    // The operator signs in again; the same work applies exactly once.
    platform.mode = 'ok';
    after.eraseBackoff();
    final run = await after.syncNow();
    expect(run.applied, 7);
    expect(platform.appliedIds.toSet(), hasLength(7));
  }, timeout: _ioTimeout);

  test('a business rejection is preserved with the platform’s reason, not retried', () async {
    final (dir, path) = await _tempQueue();
    addTearDown(() => dir.delete(recursive: true));
    final platform = _Platform();
    final client = _Client(path, platform);
    await _captureOffline(client);
    client.forceOffline = false;

    platform.mode = 'conflict';
    await client.syncNow();
    final ops = client.queue.operations;
    expect(ops.where((op) => op.state == SyncState.conflict), hasLength(7));
    expect(ops.first.conflictReason, 'center_closed');
    expect(
      ops.first.conflictDetail,
      'The centre was closed for the business date',
    );

    // The rejection is a decision, not a glitch — a later sync does not
    // resubmit it behind the operator's back.
    platform.mode = 'ok';
    client.eraseBackoff();
    final run = await client.syncNow();
    expect(run.applied, 0);
    expect(platform.appliedIds, isEmpty);
  }, timeout: _ioTimeout);

  test('a transport failure stays retryable', () async {
    final (dir, path) = await _tempQueue();
    addTearDown(() => dir.delete(recursive: true));
    final platform = _Platform();
    final client = _Client(path, platform);
    await _captureOffline(client);
    client.forceOffline = false;

    platform.mode = 'flaky';
    await client.syncNow();
    expect(
      client.queue.snapshot(online: false, running: false).conflicts,
      0,
    );

    platform.mode = 'ok';
    client.eraseBackoff();
    final run = await client.syncNow();
    expect(run.applied, 7);
  }, timeout: _ioTimeout);


}
