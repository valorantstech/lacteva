import 'dart:async';

import '../api.dart';
import 'queue.dart';

/// Drives the durable queue against the platform (OFF-001).
///
/// The engine owns *when* work is pushed; the queue owns *what* is
/// outstanding. Both are deliberately dumb about business rules — a batch is
/// replayed by the server through the same collection service an online call
/// would use, so nothing here can make a rule behave differently offline.
class SyncEngine {
  SyncEngine({
    required this.client,
    required this.queue,
    required this.deviceId,
    this.batchSize = 25,
  });

  final ApiClient client;
  final SyncQueue queue;
  final String deviceId;
  final int batchSize;

  bool _running = false;
  bool _cancelRequested = false;
  bool _online = true;

  /// Progress for the UI: (completed, total) of the current run.
  final StreamController<SyncProgress> _progress =
      StreamController<SyncProgress>.broadcast();

  Stream<SyncProgress> get progress => _progress.stream;

  bool get isRunning => _running;

  bool get isOnline => _online;

  /// Ask a running sync to stop between batches. Work already handed to the
  /// server is never abandoned — its outcome is applied first.
  void cancel() => _cancelRequested = true;

  void dispose() => _progress.close();

  /// Push every due operation, batch by batch, until the queue drains, the
  /// caller cancels, or connectivity fails.
  Future<SyncRunResult> sync({DateTime? now}) async {
    if (_running) return SyncRunResult.alreadyRunning();
    _running = true;
    _cancelRequested = false;
    await queue.load();

    var applied = 0, duplicates = 0, conflicts = 0, failed = 0, batches = 0;
    try {
      while (true) {
        if (_cancelRequested) {
          queue.releaseSyncing();
          await queue.save();
          return SyncRunResult(
            applied: applied,
            duplicates: duplicates,
            conflicts: conflicts,
            failed: failed,
            batches: batches,
            cancelled: true,
          );
        }
        final due = queue.due(now: now);
        if (due.isEmpty) break;
        final batch = due.take(batchSize).toList();
        queue.markSyncing(batch);
        await queue.save(); // survive a crash mid-push

        Map<String, dynamic> response;
        try {
          response = await client.pushSyncBatch(
            deviceId: deviceId,
            operations: batch.map((o) => o.toOperation()).toList(),
          );
          _online = true;
        } catch (e) {
          // Connectivity died mid-run. Nothing is lost: the batch returns to
          // FAILED with a backoff and the next run picks it up.
          _online = e is! ApiException;
          queue.markBatchFailed(batch, _describe(e), now: now);
          await queue.save();
          failed += batch.length;
          _emit(applied + duplicates + conflicts + failed, due.length);
          return SyncRunResult(
            applied: applied,
            duplicates: duplicates,
            conflicts: conflicts,
            failed: failed,
            batches: batches,
            error: _describe(e),
          );
        }

        final results = (response['results'] as List? ?? const [])
            .map((r) => (r as Map).cast<String, dynamic>())
            .toList();
        final byId = {for (final r in results) r['operation_id'] as String: r};
        for (final op in batch) {
          final result = byId[op.operationId];
          if (result == null) {
            // The server said nothing about it — treat as retryable rather
            // than assuming success.
            queue.markBatchFailed(
              [op],
              'no result returned for this operation',
              now: now,
            );
            failed += 1;
            continue;
          }
          queue.applyResult(op, result, now: now);
          switch (result['status']) {
            case 'applied':
              applied += 1;
            case 'duplicate':
              duplicates += 1;
            case 'conflict':
              conflicts += 1;
            default:
              failed += 1;
          }
        }
        batches += 1;
        queue.recordSyncTime(DateTime.now().toUtc());
        await queue.save();
        _emit(applied + duplicates + conflicts + failed, due.length);

        if (batch.length < batchSize) break;
      }
      await queue.prune();
      return SyncRunResult(
        applied: applied,
        duplicates: duplicates,
        conflicts: conflicts,
        failed: failed,
        batches: batches,
      );
    } finally {
      _running = false;
      _cancelRequested = false;
    }
  }

  /// Operator-initiated "try again": clears backoff on failures, then syncs.
  Future<SyncRunResult> retryFailed({DateTime? now}) async {
    await queue.load();
    queue.retryAll();
    await queue.save();
    return sync(now: now);
  }

  /// Record that a call failed for network reasons, so the UI can show the
  /// offline banner without a separate connectivity plugin: the app learns
  /// it is offline the same way the operator does — something did not work.
  void markOffline() => _online = false;

  void markOnline() => _online = true;

  void _emit(int done, int total) {
    if (!_progress.isClosed) {
      _progress.add(SyncProgress(completed: done, total: total));
    }
  }

  static String _describe(Object error) => error is ApiException
      ? error.detail
      : 'the platform could not be reached';
}

class SyncProgress {
  const SyncProgress({required this.completed, required this.total});

  final int completed;
  final int total;

  double get fraction => total == 0 ? 1 : (completed / total).clamp(0, 1);
}

class SyncRunResult {
  const SyncRunResult({
    required this.applied,
    required this.duplicates,
    required this.conflicts,
    required this.failed,
    required this.batches,
    this.cancelled = false,
    this.error,
    this.skipped = false,
  });

  factory SyncRunResult.alreadyRunning() => const SyncRunResult(
    applied: 0,
    duplicates: 0,
    conflicts: 0,
    failed: 0,
    batches: 0,
    skipped: true,
  );

  final int applied;
  final int duplicates;
  final int conflicts;
  final int failed;
  final int batches;
  final bool cancelled;
  final bool skipped;
  final String? error;

  int get total => applied + duplicates + conflicts + failed;

  bool get clean => failed == 0 && conflicts == 0 && error == null;
}
