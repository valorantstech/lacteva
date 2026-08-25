/// The delivery round (DEMO-012 §5, §7).
///
/// Designed for somebody standing at a gate with one hand free, in sun, on a
/// phone that may have no signal. That shapes every decision here:
///
/// * **The standing order is the default.** The plan already says this
///   household takes 2 litres each morning, so the common case is one tap on
///   DELIVERED. Typing a quantity is the exception, not the ritual.
/// * **Big targets.** The three outcome buttons are full-width and 56 high;
///   nothing important is smaller than a thumb.
/// * **Offline is normal, not an error.** The round is captured into a durable
///   queue and syncs later. The banner says which state you are in, always,
///   because a rider who cannot tell has to guess whether to write it down.
/// * **No money is computed here.** The app sends a quantity; the platform
///   multiplies by the agreed rate and stores the amount. `weight x rate` in
///   Dart would be a second pricing engine on the worst possible device.
library;

import 'package:flutter/material.dart';

import 'api.dart';
import 'offline/offline_client.dart';
import 'l10n.dart';
import 'session.dart';
import 'sign_out.dart';

/// The device's own UTC date — a LAST RESORT only (DEMO-013).
///
/// The round asks the platform which day it is by omitting the dates, because
/// a phone cannot compute an IANA calendar date without shipping a timezone
/// database and its own clock is not the dairy's. This is used only when the
/// platform's answer is unavailable (the reporting grant is missing, or the
/// phone is offline), where a plausible date beats no round at all.
String _deviceDate() =>
    DateTime.now().toUtc().toIso8601String().substring(0, 10);

String _money(Object? v) => v == null ? '—' : v.toString();

/// The round in the ROUTE's order, with anybody not on the route after it.
///
/// A pure function, and PUBLIC so the rule is testable without a phone, a
/// platform or a widget tree — the ordering is the one piece of real logic
/// this screen gained, so it is the piece a test should be able to reach.
/// Customers absent from the route are kept rather than hidden: a household
/// somebody forgot to add to the round still takes milk, and dropping them
/// from the screen would be the app deciding not to deliver.
List<Map<String, dynamic>> inRouteOrder(
  List<Map<String, dynamic>> customers,
  Map<String, dynamic> run,
) {
  final positions = <String, int>{};
  for (final stop in (run['stops'] as List? ?? const [])) {
    final row = stop as Map<String, dynamic>;
    positions[row['customer_id'].toString()] =
        (row['position'] as num?)?.toInt() ?? 0;
  }
  if (positions.isEmpty) return customers;

  final ordered = [...customers];
  ordered.sort((a, b) {
    // Not on the route sorts last, and keeps its own order among equals.
    final pa = positions[a['id'].toString()] ?? 1 << 30;
    final pb = positions[b['id'].toString()] ?? 1 << 30;
    return pa.compareTo(pb);
  });
  return ordered;
}

/// Today's round: every customer, and what has happened to each so far.
class DeliveryRoundScreen extends StatefulWidget {
  const DeliveryRoundScreen({
    super.key,
    required this.client,
    required this.session,
  });

  final OfflineApiClient client;
  final Session session;

  @override
  State<DeliveryRoundScreen> createState() => _DeliveryRoundScreenState();
}

class _DeliveryRoundScreenState extends State<DeliveryRoundScreen> {
  List<Map<String, dynamic>> _customers = const [];
  Map<String, Map<String, dynamic>> _doneToday = {};
  Map<String, dynamic>? _report;

  /// Today's run for this rider's route, when one has been planned
  /// (DEMO-034). Null is the ordinary case for a dairy that has not adopted
  /// routes, and the round works exactly as it did before — which is why
  /// nothing below is required for the screen to function.
  Map<String, dynamic>? _run;

  /// The dairy's today, as the platform reported it on the last load.
  String _businessDate = _deviceDate();
  bool _loading = true;
  String? _error;
  int _pending = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  /// Three calls for the whole screen, not one per customer.
  ///
  /// A round of forty households on a phone tether must not be forty round
  /// trips (DEMO-012 §13). The customer list, today's deliveries and the
  /// day's aggregate are each ONE request, joined here by id.
  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      // Ask the PLATFORM what day it is, by not telling it. It answers for
      // the dairy's timezone and echoes the dates it used, which the round
      // then uses for everything else — so a rider at 05:00 in Bengaluru gets
      // this morning's round rather than yesterday's.
      Map<String, dynamic>? report;
      try {
        report = await widget.client.deliveryReport();
      } on ApiException {
        report = null; // reporting is a separate grant; the round still works
      }
      final today = (report?['date_from'] ?? _deviceDate()).toString();
      final customers = await widget.client.listCustomers(
        status: 'active',
        limit: 100,
      );
      final delivered = await widget.client.listDeliveries(
        dateFrom: today,
        dateTo: today,
        limit: 200,
      );
      final done = <String, Map<String, dynamic>>{};
      for (final d in (delivered['items'] as List? ?? const [])) {
        final row = d as Map<String, dynamic>;
        done[row['customer_id'].toString()] = row;
      }

      // DEMO-034: which route, and in what order. A separate grant, so a
      // rider without it still gets the round — just unordered, as before.
      List<Map<String, dynamic>> runs = const [];
      try {
        runs = await widget.client.listDeliveryRuns();
      } on ApiException {
        runs = const [];
      }
      final run = runs.isEmpty ? null : runs.first;

      var list = ((customers['items'] as List?) ?? const [])
          .cast<Map<String, dynamic>>();
      if (run != null) {
        list = inRouteOrder(list, run);
      }

      if (!mounted) return;
      setState(() {
        _customers = list;
        _doneToday = done;
        _report = report;
        _run = run;
        _businessDate = today;
        _pending = widget.client.pendingCount;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.detail;
        _loading = false;
        _pending = widget.client.pendingCount;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        // Offline is not a failure on this screen. Whatever was already
        // loaded stays on screen and the round continues into the queue.
        _error = null;
        _loading = false;
        _pending = widget.client.pendingCount;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final canRecord = widget.session.can('sales.delivery.record');
    final t = L10n.of(widget.session);
    return Scaffold(
      appBar: AppBar(
        title: Text(t.t('round.title')),
        actions: [
          IconButton(
            tooltip: t.t('round.refresh'),
            onPressed: _loading ? null : _load,
            icon: const Icon(Icons.refresh),
          ),
          SignOutButton(client: widget.client, label: t.t('common.signOut')),
        ],
      ),
      body: Column(
        children: [
          _SyncBanner(pending: _pending, onSync: _sync, t: t),
          if (_report != null) _DayTotals(report: _report!, t: t),
          if (_run != null) _RunBanner(run: _run!),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _customers.isEmpty
                ? _Empty(
                    icon: Icons.people_outline,
                    title: t.t('round.empty'),
                    detail: t.t('round.emptyDetail'),
                  )
                : RefreshIndicator(
                    onRefresh: _load,
                    child: ListView.separated(
                      itemCount: _customers.length,
                      separatorBuilder: (_, _) => const Divider(height: 1),
                      itemBuilder: (context, i) {
                        final c = _customers[i];
                        final id = c['id'].toString();
                        return _CustomerRow(
                          customer: c,
                          delivered: _doneToday[id],
                          t: t,
                          onTap: canRecord ? () => _open(c) : null,
                        );
                      },
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Future<void> _sync() async {
    final result = await widget.client.syncNow();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          result.failed > 0
              ? '${result.applied} sent, ${result.failed} still queued'
              : '${result.applied} operation(s) synced',
        ),
      ),
    );
    await _load();
  }

  Future<void> _open(Map<String, dynamic> customer) async {
    final recorded = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => RecordDeliveryScreen(
          client: widget.client,
          session: widget.session,
          customer: customer,
          businessDate: _businessDate,
        ),
      ),
    );
    if (recorded == true) await _load();
  }
}

/// Online/offline and what is waiting — DEMO-012 §9.
///
/// Always present. A rider must never have to guess whether the last twenty
/// minutes of work is on the phone or on the platform.
class _SyncBanner extends StatelessWidget {
  const _SyncBanner({
    required this.pending,
    required this.onSync,
    required this.t,
  });

  final int pending;
  final Future<void> Function() onSync;
  final L10n t;

  @override
  Widget build(BuildContext context) {
    final offline = pending > 0;
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: offline
          ? scheme.tertiaryContainer
          : scheme.surfaceContainerHighest,
      child: InkWell(
        onTap: offline ? onSync : null,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          child: Row(
            children: [
              Icon(
                offline
                    ? Icons.cloud_upload_outlined
                    : Icons.cloud_done_outlined,
                size: 20,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  offline
                      ? t.t('round.waiting', {'count': pending})
                      : t.t('round.allSent'),
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
              if (offline)
                Text(
                  t.t('round.sync'),
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The day, as the DATABASE aggregated it (§7). Nothing here is summed on the
/// phone — the totals cover the whole day, not the rows that happen to be in
/// memory.
/// Which route this is, who is driving it and in what (DEMO-034).
///
/// Deliberately three facts and no numbers. Everything a rider needs to know
/// they are on the right round, and nothing about money — the day's figures
/// are `_DayTotals`' job, and the run does not know them.
class _RunBanner extends StatelessWidget {
  const _RunBanner({required this.run});

  final Map<String, dynamic> run;

  @override
  Widget build(BuildContext context) {
    final route = (run['route_name'] ?? run['route_code'] ?? '').toString();
    final driver = (run['driver_name'] ?? '').toString();
    final vehicle = (run['vehicle_registration'] ?? '').toString();
    final status = (run['status'] ?? '').toString();

    final parts = <String>[
      if (driver.isNotEmpty) driver,
      if (vehicle.isNotEmpty) vehicle,
    ];
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      color: Theme.of(context).colorScheme.secondaryContainer,
      child: Row(
        children: [
          const Icon(Icons.alt_route, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(route, style: Theme.of(context).textTheme.titleSmall),
                if (parts.isNotEmpty)
                  Text(
                    parts.join(' · '),
                    style: Theme.of(context).textTheme.labelSmall,
                  ),
              ],
            ),
          ),
          Text(status, style: Theme.of(context).textTheme.labelMedium),
        ],
      ),
    );
  }
}

class _DayTotals extends StatelessWidget {
  const _DayTotals({required this.report, required this.t});

  final Map<String, dynamic> report;
  final L10n t;

  @override
  Widget build(BuildContext context) {
    // P1-LOCALE-I18N-001: these four keys existed in all three catalogs and
    // the tiles retyped their English — wired now.
    final cells = <(String, String)>[
      (t.t('round.delivered'), '${report['deliveries'] ?? 0}'),
      (t.t('round.customers'), '${report['customers_served'] ?? 0}'),
      (
        t.t('round.quantity'),
        '${report['total_quantity'] ?? 0} ${report['quantity_unit'] ?? 'L'}',
      ),
      (t.t('round.value'), _money(report['total_amount'])),
    ];
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      color: Theme.of(context).colorScheme.surfaceContainerLow,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          for (final (label, value) in cells)
            Column(
              children: [
                Text(value, style: Theme.of(context).textTheme.titleMedium),
                Text(label, style: Theme.of(context).textTheme.labelSmall),
              ],
            ),
        ],
      ),
    );
  }
}

class _CustomerRow extends StatelessWidget {
  const _CustomerRow({
    required this.customer,
    required this.delivered,
    required this.t,
    required this.onTap,
  });

  final Map<String, dynamic> customer;
  final Map<String, dynamic>? delivered;
  final L10n t;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final status = delivered?['status']?.toString();
    final done = status == 'delivered';
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      leading: CircleAvatar(
        radius: 22,
        backgroundColor: done
            ? Colors.green.shade100
            : status != null
            ? Colors.orange.shade100
            : Theme.of(context).colorScheme.surfaceContainerHighest,
        child: Icon(
          done
              ? Icons.check
              : status != null
              ? Icons.remove
              : Icons.local_shipping_outlined,
          color: done ? Colors.green.shade800 : null,
        ),
      ),
      title: Text(
        customer['name']?.toString() ?? '—',
        style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w500),
      ),
      subtitle: Text(
        status == null
            ? '${customer['code'] ?? ''} · ${t.t('round.notRecorded')}'
            // The status arrives as a CODE and is translated here. It used to
            // be printed raw, so a Hindi-speaking rider read the English word
            // the database happens to store (DEMO-016).
            : '${customer['code'] ?? ''} · ${t.t('status.$status')}'
                  '${delivered?['quantity'] != null ? ' ${delivered!['quantity']} ${delivered!['quantity_unit'] ?? 'L'}' : ''}',
      ),
      trailing: onTap == null
          ? null
          : const Icon(Icons.chevron_right, size: 28),
      onTap: onTap,
    );
  }
}

/// One delivery. Three big buttons and, only if you need it, a quantity.
class RecordDeliveryScreen extends StatefulWidget {
  const RecordDeliveryScreen({
    super.key,
    required this.client,
    required this.session,
    required this.customer,
    required this.businessDate,
  });

  final OfflineApiClient client;
  final Session session;
  final Map<String, dynamic> customer;

  /// The dairy's own date for this round, as the PLATFORM reported it
  /// (DEMO-013). Passed down rather than recomputed here: the phone's clock
  /// is not the dairy's, and a delivery filed under the wrong day lands on
  /// the wrong month's bill.
  final String businessDate;

  @override
  State<RecordDeliveryScreen> createState() => _RecordDeliveryScreenState();
}

class _RecordDeliveryScreenState extends State<RecordDeliveryScreen> {
  final _quantity = TextEditingController();
  String _slot = 'morning';
  bool _busy = false;
  String? _error;
  bool _queued = false;

  @override
  void dispose() {
    _quantity.dispose();
    super.dispose();
  }

  Future<void> _record(String status) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await widget.client.recordDeliveryOffline(
        customerId: widget.customer['id'].toString(),
        deliveryDate: widget.businessDate,
        slot: _slot,
        status: status,
        // Empty means "the standing order", which the platform reads from the
        // customer's plan. The app does not invent a default quantity.
        quantity: _quantity.text.trim(),
      );
      if (!mounted) return;
      setState(() => _queued = result['_queued'] == true);
      Navigator.of(context).pop(true);
      final t = L10n.of(widget.session);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _queued ? t.t('record.queued') : t.t('record.recorded'),
          ),
        ),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.detail);
    } catch (_) {
      // P1-PRODUCT-READINESS-001 R-1: a transport failure is not a platform
      // refusal. Without this the save silently did nothing — the busy flag
      // cleared, no message appeared, and the operator could reasonably
      // conclude the record had been saved. The load paths gained this in
      // P0-PRODUCT-009; the save paths are a different shape and were missed.
      if (!mounted) return;
      setState(() => _error = L10n.of(null).t('common.couldNotReach'));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.customer;
    final t = L10n.of(widget.session);
    return Scaffold(
      appBar: AppBar(title: Text(c['name']?.toString() ?? t.t('record.title'))),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      c['name']?.toString() ?? '',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 4),
                    Text('${c['code'] ?? ''} · ${c['customer_type'] ?? ''}'),
                    if ((c['address'] ?? '').toString().isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(c['address'].toString()),
                      ),
                    if ((c['phone'] ?? '').toString().isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(c['phone'].toString()),
                      ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            SegmentedButton<String>(
              segments: [
                ButtonSegment(
                  value: 'morning',
                  label: Text(t.t('slot.morning')),
                ),
                ButtonSegment(
                  value: 'evening',
                  label: Text(t.t('slot.evening')),
                ),
              ],
              selected: {_slot},
              onSelectionChanged: (s) => setState(() => _slot = s.first),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _quantity,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              style: const TextStyle(fontSize: 22),
              decoration: InputDecoration(
                labelText: t.t('record.quantityHint'),
                border: const OutlineInputBorder(),
                // The note is not decoration. An operator who believes they
                // are typing a price will eventually type one.
                helperText: t.t('record.amountNote'),
                helperMaxLines: 3,
              ),
            ),
            const SizedBox(height: 20),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            _BigButton(
              label: t.t('record.delivered'),
              icon: Icons.check_circle_outline,
              color: Colors.green.shade700,
              onPressed: _busy ? null : () => _record('delivered'),
            ),
            const SizedBox(height: 12),
            _BigButton(
              label: t.t('record.notDelivered'),
              icon: Icons.cancel_outlined,
              color: Colors.orange.shade800,
              onPressed: _busy ? null : () => _record('skipped'),
            ),
            const SizedBox(height: 12),
            _BigButton(
              label: t.t('record.returned'),
              icon: Icons.undo,
              color: Colors.blueGrey.shade700,
              onPressed: _busy ? null : () => _record('returned'),
            ),
          ],
        ),
      ),
    );
  }
}

class _BigButton extends StatelessWidget {
  const _BigButton({
    required this.label,
    required this.icon,
    required this.color,
    required this.onPressed,
  });

  final String label;
  final IconData icon;
  final Color color;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 56,
      child: FilledButton.icon(
        style: FilledButton.styleFrom(backgroundColor: color),
        onPressed: onPressed,
        icon: Icon(icon, size: 26),
        label: Text(label, style: const TextStyle(fontSize: 17)),
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
            Icon(icon, size: 48, color: Theme.of(context).disabledColor),
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
