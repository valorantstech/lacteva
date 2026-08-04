import 'package:flutter/material.dart';

import 'offline_client.dart';
import 'queue.dart';
import 'sync_engine.dart';

/// A thin strip that tells the operator the truth about connectivity and the
/// queue (OFF-001).
///
/// Deliberately never blocks: an operator at 5 a.m. with a queue of farmers
/// must be able to keep collecting whatever this says.
class OfflineBanner extends StatelessWidget {
  const OfflineBanner({super.key, required this.client, this.onTap});

  final OfflineApiClient client;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final snapshot = client.snapshot();
    final scheme = Theme.of(context).colorScheme;
    if (snapshot.online && !snapshot.hasWork && snapshot.conflicts == 0) {
      return const SizedBox.shrink();
    }
    final offline = !snapshot.online;
    final colour = offline
        ? scheme.errorContainer
        : snapshot.conflicts > 0
        ? Colors.orange.shade100
        : scheme.secondaryContainer;
    return Material(
      color: colour,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Row(
            children: [
              Icon(offline ? Icons.cloud_off : Icons.sync, size: 18),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  offline
                      ? 'Offline — collections are saved on this device '
                            '(${snapshot.outstanding} waiting)'
                      : snapshot.conflicts > 0
                      ? '${snapshot.conflicts} item(s) need attention'
                      : 'Syncing ${snapshot.outstanding} item(s)…',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
              if (onTap != null) const Icon(Icons.chevron_right, size: 18),
            ],
          ),
        ),
      ),
    );
  }
}

/// The queue screen: what is waiting, what failed, what needs a decision.
class SyncStatusScreen extends StatefulWidget {
  const SyncStatusScreen({super.key, required this.client});

  final OfflineApiClient client;

  @override
  State<SyncStatusScreen> createState() => _SyncStatusScreenState();
}

class _SyncStatusScreenState extends State<SyncStatusScreen> {
  SyncRunResult? _lastRun;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    widget.client.queue.load().then((_) {
      if (mounted) setState(() {});
    });
  }

  Future<void> _sync({bool retryFailed = false}) async {
    setState(() => _busy = true);
    final result = retryFailed
        ? await widget.client.engine.retryFailed()
        : await widget.client.syncNow();
    if (!mounted) return;
    setState(() {
      _lastRun = result;
      _busy = false;
    });
  }

  String _ago(DateTime? at) {
    if (at == null) return 'never';
    final delta = DateTime.now().toUtc().difference(at);
    if (delta.inMinutes < 1) return 'just now';
    if (delta.inHours < 1) return '${delta.inMinutes} min ago';
    if (delta.inDays < 1) return '${delta.inHours} h ago';
    return '${delta.inDays} d ago';
  }

  @override
  Widget build(BuildContext context) {
    final snapshot = widget.client.snapshot();
    final operations = widget.client.queue.operations.reversed.toList();
    final conflicts = operations
        .where((o) => o.state == SyncState.conflict)
        .toList();
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Sync'),
        actions: [
          if (_busy)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Center(
                child: SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            )
          else
            IconButton(
              tooltip: 'Sync now',
              icon: const Icon(Icons.sync),
              onPressed: () => _sync(),
            ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: ListTile(
              leading: Icon(
                snapshot.online ? Icons.cloud_done : Icons.cloud_off,
                color: snapshot.online ? Colors.green : scheme.error,
              ),
              title: Text(snapshot.online ? 'Online' : 'Offline'),
              subtitle: Text(
                'Last successful sync: ${_ago(snapshot.lastSyncAt)}',
              ),
            ),
          ),
          Row(
            children: [
              _Tile(label: 'Pending', value: snapshot.pending),
              _Tile(label: 'Synced', value: snapshot.synced),
              _Tile(
                label: 'Failed',
                value: snapshot.failed,
                tone: snapshot.failed > 0 ? scheme.error : null,
              ),
              _Tile(
                label: 'Conflicts',
                value: snapshot.conflicts,
                tone: snapshot.conflicts > 0 ? Colors.orange : null,
              ),
            ],
          ),
          const SizedBox(height: 8),
          if (_lastRun != null)
            Card(
              child: ListTile(
                dense: true,
                leading: Icon(
                  _lastRun!.clean
                      ? Icons.check_circle_outline
                      : Icons.info_outline,
                  color: _lastRun!.clean ? Colors.green : Colors.orange,
                ),
                title: Text(
                  'Last run: ${_lastRun!.applied} applied, '
                  '${_lastRun!.duplicates} already there, '
                  '${_lastRun!.conflicts} conflict(s), ${_lastRun!.failed} failed',
                ),
                subtitle: _lastRun!.error != null
                    ? Text(_lastRun!.error!)
                    : _lastRun!.cancelled
                    ? const Text('Cancelled — nothing was lost')
                    : null,
              ),
            ),
          Row(
            children: [
              if (snapshot.failed > 0)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: FilledButton.tonalIcon(
                    onPressed: _busy ? null : () => _sync(retryFailed: true),
                    icon: const Icon(Icons.refresh),
                    label: const Text('Retry failed'),
                  ),
                ),
              if (widget.client.engine.isRunning)
                OutlinedButton.icon(
                  onPressed: widget.client.engine.cancel,
                  icon: const Icon(Icons.stop_circle_outlined),
                  label: const Text('Cancel'),
                ),
            ],
          ),
          if (conflicts.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(
              'Needs attention (${conflicts.length})',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            ...conflicts.map(
              (op) => Card(
                child: ListTile(
                  leading: Icon(Icons.warning_amber, color: Colors.orange),
                  title: Text(_readable(op.kind)),
                  subtitle: Text(
                    '${_conflictLabel(op.conflictReason)}\n'
                    '${op.conflictDetail ?? ''}',
                  ),
                  isThreeLine: true,
                  onTap: () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => ConflictDetailScreen(operation: op),
                    ),
                  ),
                ),
              ),
            ),
          ],
          const SizedBox(height: 12),
          Text(
            'Queue (${operations.length})',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          if (operations.isEmpty)
            const ListTile(dense: true, title: Text('Nothing captured yet.')),
          ...operations
              .take(50)
              .map(
                (op) => ListTile(
                  dense: true,
                  leading: Icon(
                    _stateIcon(op.state),
                    color: _stateColour(op.state, scheme),
                  ),
                  title: Text(_readable(op.kind)),
                  subtitle: Text(
                    '${op.state.name}'
                    '${op.attempts > 0 ? ' · attempt ${op.attempts}' : ''}'
                    ' · ${op.recordedAt.toIso8601String().replaceFirst('T', ' ').split('.').first}',
                  ),
                ),
              ),
        ],
      ),
    );
  }
}

/// One conflict, explained in the operator's terms with the platform's own
/// detail underneath — never a silent overwrite, never a mystery.
class ConflictDetailScreen extends StatelessWidget {
  const ConflictDetailScreen({super.key, required this.operation});

  final QueuedOperation operation;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_readable(operation.kind))),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: ListTile(
              leading: const Icon(Icons.warning_amber, color: Colors.orange),
              title: Text(_conflictLabel(operation.conflictReason)),
              subtitle: Text(operation.conflictDetail ?? ''),
            ),
          ),
          const SizedBox(height: 8),
          ListTile(
            dense: true,
            leading: const Icon(Icons.schedule),
            title: const Text('Captured'),
            subtitle: Text(
              operation.recordedAt
                  .toIso8601String()
                  .replaceFirst('T', ' ')
                  .split('.')
                  .first,
            ),
          ),
          ListTile(
            dense: true,
            leading: const Icon(Icons.tag),
            title: const Text('Operation'),
            subtitle: Text(operation.operationId),
          ),
          if (operation.serverId != null)
            ListTile(
              dense: true,
              leading: const Icon(Icons.cloud_done_outlined),
              title: const Text('Recorded on the platform as'),
              subtitle: Text(operation.serverId!),
            ),
          const Padding(
            padding: EdgeInsets.all(16),
            child: Text(
              'This item was not applied silently. Resolve it with your '
              'supervisor in the portal — the captured data stays on this '
              'device until then.',
            ),
          ),
        ],
      ),
    );
  }
}

class _Tile extends StatelessWidget {
  const _Tile({required this.label, required this.value, this.tone});

  final String label;
  final int value;
  final Color? tone;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Card(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Column(
            children: [
              Text(
                '$value',
                style: Theme.of(
                  context,
                ).textTheme.titleLarge?.copyWith(color: tone),
              ),
              Text(label, style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ),
      ),
    );
  }
}

String _readable(String kind) => switch (kind) {
  'open_session' => 'Open collection session',
  'close_session' => 'Close collection session',
  'create_transaction' => 'Start collection',
  'identify_supplier' => 'Identify supplier',
  'receive_milk' => 'Receive milk',
  'capture_weight' => 'Capture weight',
  'capture_quality' => 'Capture quality',
  'accept' => 'Accept milk',
  'reject' => 'Reject milk',
  'complete' => 'Complete collection',
  'cancel' => 'Cancel collection',
  _ => kind,
};

String _conflictLabel(String? reason) => switch (reason) {
  'already_accepted' => 'Already recorded on the platform',
  'supplier_unavailable' => 'Supplier is no longer active',
  'session_closed' => 'The collection session was closed',
  'rate_card_changed' =>
    'Prices changed — the collection was kept, the amount differs',
  'unresolved_reference' => 'Waiting for an earlier step to sync',
  'invalid_state' => 'The platform refused this step',
  _ => 'Needs attention',
};

IconData _stateIcon(SyncState state) => switch (state) {
  SyncState.synced => Icons.check_circle_outline,
  SyncState.failed => Icons.error_outline,
  SyncState.conflict => Icons.warning_amber,
  SyncState.syncing => Icons.sync,
  SyncState.pending => Icons.schedule,
};

Color _stateColour(SyncState state, ColorScheme scheme) => switch (state) {
  SyncState.synced => Colors.green,
  SyncState.failed => scheme.error,
  SyncState.conflict => Colors.orange,
  SyncState.syncing => scheme.primary,
  SyncState.pending => scheme.outline,
};
