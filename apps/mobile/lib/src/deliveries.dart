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
import 'session.dart';

String _today() => DateTime.now().toUtc().toIso8601String().substring(0, 10);

String _money(Object? v) => v == null ? '—' : v.toString();

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
      final today = _today();
      final customers = await widget.client.listCustomers(
        status: 'active',
        limit: 100,
      );
      final delivered = await widget.client.listDeliveries(
        dateFrom: today,
        dateTo: today,
        limit: 200,
      );
      Map<String, dynamic>? report;
      try {
        report = await widget.client.deliveryReport(
          dateFrom: today,
          dateTo: today,
        );
      } on ApiException {
        report = null; // reporting is a separate grant; the round still works
      }
      final done = <String, Map<String, dynamic>>{};
      for (final d in (delivered['items'] as List? ?? const [])) {
        final row = d as Map<String, dynamic>;
        done[row['customer_id'].toString()] = row;
      }
      if (!mounted) return;
      setState(() {
        _customers = ((customers['items'] as List?) ?? const [])
            .cast<Map<String, dynamic>>();
        _doneToday = done;
        _report = report;
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
    return Scaffold(
      appBar: AppBar(
        title: const Text("Today's round"),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: _loading ? null : _load,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: Column(
        children: [
          _SyncBanner(pending: _pending, onSync: _sync),
          if (_report != null) _DayTotals(report: _report!),
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
                ? const _Empty(
                    icon: Icons.people_outline,
                    title: 'No customers on this round',
                    detail:
                        'Customers appear here once the dairy registers them.',
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
  const _SyncBanner({required this.pending, required this.onSync});

  final int pending;
  final Future<void> Function() onSync;

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
                      ? '$pending delivery(s) saved on this phone — tap to send'
                      : 'All deliveries sent',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
              if (offline)
                const Text(
                  'SEND',
                  style: TextStyle(fontWeight: FontWeight.bold),
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
class _DayTotals extends StatelessWidget {
  const _DayTotals({required this.report});

  final Map<String, dynamic> report;

  @override
  Widget build(BuildContext context) {
    final cells = <(String, String)>[
      ('Delivered', '${report['deliveries'] ?? 0}'),
      ('Customers', '${report['customers_served'] ?? 0}'),
      (
        'Quantity',
        '${report['total_quantity'] ?? 0} ${report['quantity_unit'] ?? 'L'}',
      ),
      ('Value', _money(report['total_amount'])),
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
    required this.onTap,
  });

  final Map<String, dynamic> customer;
  final Map<String, dynamic>? delivered;
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
            ? '${customer['code'] ?? ''} · not yet recorded'
            : '${customer['code'] ?? ''} · $status'
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
  });

  final OfflineApiClient client;
  final Session session;
  final Map<String, dynamic> customer;

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
        deliveryDate: _today(),
        slot: _slot,
        status: status,
        // Empty means "the standing order", which the platform reads from the
        // customer's plan. The app does not invent a default quantity.
        quantity: _quantity.text.trim(),
      );
      if (!mounted) return;
      setState(() => _queued = result['_queued'] == true);
      Navigator.of(context).pop(true);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _queued
                ? 'Saved on this phone — it will send when there is signal'
                : 'Recorded',
          ),
        ),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.customer;
    return Scaffold(
      appBar: AppBar(title: Text(c['name']?.toString() ?? 'Delivery')),
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
              segments: const [
                ButtonSegment(value: 'morning', label: Text('Morning')),
                ButtonSegment(value: 'evening', label: Text('Evening')),
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
              decoration: const InputDecoration(
                labelText: 'Quantity (leave blank for the standing order)',
                border: OutlineInputBorder(),
                helperText:
                    'The amount is calculated by the platform from the '
                    'agreed rate — it is never entered here.',
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
              label: 'DELIVERED',
              icon: Icons.check_circle_outline,
              color: Colors.green.shade700,
              onPressed: _busy ? null : () => _record('delivered'),
            ),
            const SizedBox(height: 12),
            _BigButton(
              label: 'NOT DELIVERED',
              icon: Icons.cancel_outlined,
              color: Colors.orange.shade800,
              onPressed: _busy ? null : () => _record('skipped'),
            ),
            const SizedBox(height: 12),
            _BigButton(
              label: 'RETURNED',
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
