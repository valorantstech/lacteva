/// The delivery driver's day (P0-MOB-001 / P0-MOB-002).
///
/// Designed like the operator round — for one hand, in sun, with no signal —
/// but for a different person: a DRIVER sees only the runs assigned to their
/// own linked profile, and nothing else in the dairy. The platform enforces
/// that (another driver's run is a 404); this screen just renders it calmly.
///
/// * **Outcomes are offline-first.** Delivered / skipped / returned go through
///   the same durable queue as the operator round, each carrying the
///   idempotency key the platform will recognise on replay.
/// * **Start and complete are online-first, deliberately.** A run transition
///   needs the platform's answer now — BR-0028 may refuse a run with no
///   vehicle — and a driver can keep recording outcomes offline regardless.
/// * **No money is computed or shown here.** The rate lives on the plan and
///   the arithmetic is the platform's.
/// * **Two calm empty states**: "not set up as a driver" (no linked profile)
///   and "no run today" — distinguishable because `/v1/drivers/me` answers
///   404 for the first and 200 for the second.
library;

import 'package:flutter/material.dart';

import 'api.dart';
import 'l10n.dart';
import 'offline/offline_client.dart';
import 'session.dart';

class DriverHomeScreen extends StatefulWidget {
  const DriverHomeScreen({
    super.key,
    required this.client,
    required this.session,
  });

  final OfflineApiClient client;
  final Session session;

  @override
  State<DriverHomeScreen> createState() => _DriverHomeScreenState();
}

class _DriverHomeScreenState extends State<DriverHomeScreen> {
  List<Map<String, dynamic>> _runs = const [];
  bool _linked = true;
  bool _loading = true;
  String? _error;
  int _pending = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  /// Two calls for the whole screen: the profile (to tell the empty states
  /// apart) and today's runs with their stops already on them.
  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      var linked = true;
      try {
        await widget.client.driverMe();
      } on ApiException catch (e) {
        if (e.status == 404) {
          linked = false;
        } else {
          rethrow;
        }
      }
      final runs = linked ? await widget.client.myRuns() : const <Map<String, dynamic>>[];
      if (!mounted) return;
      setState(() {
        _linked = linked;
        _runs = runs;
        _pending = widget.client.pendingCount;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.detail;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        // Offline is not a failure: whatever was loaded stays, outcomes queue.
        _error = null;
        _loading = false;
        _pending = widget.client.pendingCount;
      });
    }
  }

  Future<void> _sync() async {
    await widget.client.syncNow();
    if (!mounted) return;
    await _load();
  }

  Future<void> _transition(String runId, bool start) async {
    final t = L10n.of(widget.session);
    try {
      if (start) {
        await widget.client.startMyRun(runId);
      } else {
        await widget.client.completeMyRun(runId);
      }
      await _load();
    } on ApiException catch (e) {
      // The platform's refusal is the message — shown verbatim.
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(e.detail)));
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(t.t('driver.needsSignal'))));
    }
  }

  Future<void> _recordOutcome(
    Map<String, dynamic> run,
    Map<String, dynamic> stop,
    String status, {
    String? notes,
  }) async {
    try {
      await widget.client.recordRunOutcomeOffline(
        runId: run['id'].toString(),
        customerId: stop['customer_id'].toString(),
        status: status,
        notes: notes,
      );
      await _load();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(e.detail)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = L10n.of(widget.session);
    return Scaffold(
      appBar: AppBar(
        title: Text(t.t('driver.title')),
        actions: [
          IconButton(
            tooltip: t.t('round.refresh'),
            onPressed: _loading ? null : _load,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: Column(
        children: [
          if (_pending > 0)
            MaterialBanner(
              content: Text(t.t('driver.pending', {'count': _pending})),
              actions: [
                TextButton(onPressed: _sync, child: Text(t.t('driver.sync'))),
              ],
            ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          Expanded(child: _body(t)),
        ],
      ),
    );
  }

  Widget _body(L10n t) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (!_linked) {
      return _Empty(
        icon: Icons.badge_outlined,
        title: t.t('driver.notLinked'),
        detail: t.t('driver.notLinkedDetail'),
      );
    }
    if (_runs.isEmpty) {
      return _Empty(
        icon: Icons.free_breakfast_outlined,
        title: t.t('driver.noRun'),
        detail: t.t('driver.noRunDetail'),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        children: [for (final run in _runs) _RunCard(run: run, state: this)],
      ),
    );
  }
}

class _RunCard extends StatelessWidget {
  const _RunCard({required this.run, required this.state});

  final Map<String, dynamic> run;
  final _DriverHomeScreenState state;

  @override
  Widget build(BuildContext context) {
    final t = L10n.of(state.widget.session);
    final status = (run['status'] ?? '').toString();
    final stops = ((run['stops'] as List?) ?? const [])
        .cast<Map<String, dynamic>>();
    final remaining = stops
        .where((s) => s['delivery_status'] == null || s['delivery_status'] == 'scheduled')
        .length;

    return Card(
      margin: const EdgeInsets.all(12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.alt_route, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '${run['route_name'] ?? run['route_code'] ?? ''}',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                Chip(label: Text(status)),
              ],
            ),
            Text(
              [
                '${run['business_date']}',
                '${run['slot']}',
                if ((run['vehicle_registration'] ?? '') != '')
                  '${run['vehicle_registration']}',
              ].join(' · '),
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 8),
            if (status == 'planned')
              SizedBox(
                width: double.infinity,
                height: 52,
                child: FilledButton.icon(
                  onPressed: () => state._transition(run['id'].toString(), true),
                  icon: const Icon(Icons.play_arrow),
                  label: Text(t.t('driver.start')),
                ),
              ),
            if (status == 'in_progress' && remaining == 0)
              SizedBox(
                width: double.infinity,
                height: 52,
                child: FilledButton.icon(
                  onPressed: () =>
                      state._transition(run['id'].toString(), false),
                  icon: const Icon(Icons.flag),
                  label: Text(t.t('driver.complete')),
                ),
              ),
            if (status == 'in_progress' && remaining > 0)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Text(
                  t.t('driver.remaining', {'count': remaining}),
                  style: Theme.of(context).textTheme.labelMedium,
                ),
              ),
            const Divider(),
            for (final stop in stops) _StopTile(run: run, stop: stop, state: state),
          ],
        ),
      ),
    );
  }
}

class _StopTile extends StatelessWidget {
  const _StopTile({required this.run, required this.stop, required this.state});

  final Map<String, dynamic> run;
  final Map<String, dynamic> stop;
  final _DriverHomeScreenState state;

  @override
  Widget build(BuildContext context) {
    final t = L10n.of(state.widget.session);
    final outcome = stop['delivery_status'] as String?;
    final open = outcome == null || outcome == 'scheduled';
    final runOpen =
        run['status'] == 'in_progress' || run['status'] == 'planned';
    final address = (stop['address'] ?? '').toString();

    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: CircleAvatar(
        radius: 14,
        child: Text('${stop['position']}'),
      ),
      title: Text('${stop['name']}'),
      subtitle: address.isEmpty ? null : Text(address),
      trailing: open
          ? (runOpen
                ? FilledButton.tonal(
                    onPressed: () => _sheet(context, t),
                    child: Text(t.t('driver.record')),
                  )
                : null)
          : Chip(label: Text(t.t('driver.outcome.$outcome'))),
    );
  }

  void _sheet(BuildContext context, L10n t) {
    showModalBottomSheet<void>(
      context: context,
      builder: (sheet) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                '${stop['name']}',
                style: Theme.of(sheet).textTheme.titleMedium,
              ),
              if ((stop['phone'] ?? '') != '')
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text('${stop['phone']}'),
                ),
              const SizedBox(height: 16),
              SizedBox(
                height: 56,
                child: FilledButton(
                  onPressed: () {
                    Navigator.pop(sheet);
                    state._recordOutcome(run, stop, 'delivered');
                  },
                  child: Text(t.t('driver.outcome.delivered')),
                ),
              ),
              const SizedBox(height: 8),
              SizedBox(
                height: 56,
                child: OutlinedButton(
                  onPressed: () {
                    Navigator.pop(sheet);
                    state._recordOutcome(
                      run,
                      stop,
                      'skipped',
                      notes: t.t('driver.skippedDefaultNote'),
                    );
                  },
                  child: Text(t.t('driver.outcome.skipped')),
                ),
              ),
              const SizedBox(height: 8),
              SizedBox(
                height: 44,
                child: TextButton(
                  onPressed: () {
                    Navigator.pop(sheet);
                    state._recordOutcome(run, stop, 'returned');
                  },
                  child: Text(t.t('driver.outcome.returned')),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Empty extends StatelessWidget {
  const _Empty({required this.icon, required this.title, required this.detail});

  final IconData icon;
  final String title;
  final String detail;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 48, color: Theme.of(context).colorScheme.outline),
            const SizedBox(height: 12),
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            Text(detail, textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}
