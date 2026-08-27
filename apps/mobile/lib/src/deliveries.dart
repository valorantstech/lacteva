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
import 'theme.dart';

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
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            _SyncBanner(pending: _pending, onSync: _sync, t: t),
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
                  : RefreshIndicator(
                      onRefresh: _load,
                      child: ListView(
                        padding: EdgeInsets.zero,
                        children: [
                          _RoundHeader(
                            businessDate: _businessDate,
                            customers: _customers.length,
                            run: _run,
                            t: t,
                            onSignOut: SignOutButton(
                              client: widget.client,
                              label: t.t('common.signOut'),
                            ),
                          ),
                          // Reporting is its own grant. Without it the round
                          // still works — it simply has no figures, which is
                          // the behaviour this screen has always had.
                          if (_report != null)
                            _RoundFigures(report: _report!, t: t),
                          if (_customers.isEmpty)
                            _Empty(
                              icon: Icons.people_outline,
                              title: t.t('round.empty'),
                              detail: t.t('round.emptyDetail'),
                            )
                          else
                            for (final c in _customers)
                              Padding(
                                padding: const EdgeInsets.fromLTRB(20, 0, 20, 9),
                                child: _RoundRow(
                                  customer: c,
                                  delivered: _doneToday[c['id'].toString()],
                                  session: widget.session,
                                  t: t,
                                  onOpen: canRecord ? () => _open(c) : null,
                                  onDeliver: canRecord
                                      ? (quantity) => _deliver(c, quantity)
                                      : null,
                                ),
                              ),
                          const SizedBox(height: 26),
                        ],
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  /// The fast path: one tap, the standing order, done.
  ///
  /// Exactly the call `RecordDeliveryScreen` makes, with exactly its contract
  /// — an EMPTY quantity means "the standing order", which the platform reads
  /// from the customer's plan. The app has never invented a default quantity
  /// and does not start now; the stepper only speaks when the rider overrides.
  Future<void> _deliver(Map<String, dynamic> customer, String quantity) async {
    final t = L10n.of(widget.session);
    try {
      final result = await widget.client.recordDeliveryOffline(
        customerId: customer['id'].toString(),
        deliveryDate: _businessDate,
        // The round is generated per slot; morning is the round this screen
        // shows, and the full slot choice stays on the detail screen.
        slot: 'morning',
        status: 'delivered',
        quantity: quantity,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            result['_queued'] == true
                ? t.t('record.queued')
                : t.t('record.recorded'),
          ),
        ),
      );
      await _load();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(e.detail)));
    } catch (_) {
      // Transport failure is not a platform refusal (P0-PRODUCT-008 D-1).
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(t.t('common.couldNotReach'))));
    }
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
    final waiting = pending > 0;
    return Material(
      color: waiting ? LactevaColors.warningTint : LactevaColors.successTint,
      child: InkWell(
        onTap: waiting ? onSync : null,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
          child: Row(
            children: [
              Icon(
                waiting
                    ? Icons.cloud_upload_outlined
                    : Icons.cloud_done_outlined,
                size: 20,
                color: waiting
                    ? LactevaColors.onWarningTint
                    : LactevaColors.onSuccessTint,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  waiting
                      ? t.t('round.waiting', {'count': pending})
                      : t.t('round.allSent'),
                  style: TextStyle(
                    fontSize: 13.5,
                    color: waiting
                        ? LactevaColors.onWarningTint
                        : LactevaColors.onSuccessTint,
                  ),
                ),
              ),
              if (waiting)
                Text(
                  t.t('round.sync'),
                  style: const TextStyle(
                    fontSize: 13.5,
                    fontWeight: FontWeight.w700,
                    color: LactevaColors.onWarningTint,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Which day, how many households, and which route (DEMO-034).
///
/// The date is rendered exactly as the PLATFORM sent it. A phone cannot turn
/// an ISO date into "Wed 27 Aug" for the dairy's calendar without shipping a
/// timezone database, and a round filed under the wrong day lands on the wrong
/// month's invoice — so the board's friendly date is the platform's plain one.
class _RoundHeader extends StatelessWidget {
  const _RoundHeader({
    required this.businessDate,
    required this.customers,
    required this.run,
    required this.t,
    required this.onSignOut,
  });

  final String businessDate;
  final int customers;
  final Map<String, dynamic>? run;
  final L10n t;
  final Widget onSignOut;

  @override
  Widget build(BuildContext context) {
    final r = run;
    final route = r == null
        ? ''
        : (r['route_name'] ?? r['route_code'] ?? '').toString();
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  t.t('round.title'),
                  style: const TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.44,
                    color: LactevaColors.ink,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  [
                    businessDate,
                    t.t('round.customerCount', {'count': customers}),
                    if (route.isNotEmpty) route,
                    t.t('round.fromStandingOrders'),
                  ].join(' · '),
                  style: const TextStyle(
                    fontSize: 13.5,
                    color: LactevaColors.muted,
                  ),
                ),
              ],
            ),
          ),
          onSignOut,
        ],
      ),
    );
  }
}

/// The day, as the DATABASE aggregated it (§7).
///
/// Nothing here is summed on the phone — the totals cover the whole day, not
/// the rows that happen to be in memory. The board's third figure was money
/// collected at the door; no read links a customer payment to a round or a
/// day, so this shows the day's delivered VALUE, which the report does
/// compute, and says so.
class _RoundFigures extends StatelessWidget {
  const _RoundFigures({required this.report, required this.t});

  final Map<String, dynamic> report;
  final L10n t;

  @override
  Widget build(BuildContext context) {
    final unit = (report['quantity_unit'] ?? 'L').toString();
    final cells = <(String, String)>[
      (
        '${report['planned_quantity'] ?? report['total_quantity'] ?? 0} $unit',
        t.t('round.toDeliver'),
      ),
      (
        '${report['deliveries'] ?? 0} / ${report['planned'] ?? report['customers_served'] ?? 0}',
        t.t('round.done'),
      ),
      (_money(report['total_amount']), t.t('round.value')),
    ];
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 4, 20, 16),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        decoration: BoxDecoration(
          gradient: paleGradient(),
          border: Border.all(color: LactevaColors.paleTintBorder),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            for (final (value, label) in cells)
              Expanded(
                child: Padding(
                  padding: const EdgeInsetsDirectional.only(end: 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      FittedBox(
                        fit: BoxFit.scaleDown,
                        alignment: AlignmentDirectional.centerStart,
                        child: Text(
                          value,
                          maxLines: 1,
                          style: const TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.w700,
                            color: LactevaColors.ink,
                          ),
                        ),
                      ),
                      const SizedBox(height: 1),
                      Text(
                        label,
                        style: const TextStyle(
                          fontSize: 11.5,
                          color: LactevaColors.muted,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// One household: pending with a stepper, or done with its outcome.
class _RoundRow extends StatelessWidget {
  const _RoundRow({
    required this.customer,
    required this.delivered,
    required this.session,
    required this.t,
    required this.onOpen,
    required this.onDeliver,
  });

  final Map<String, dynamic> customer;
  final Map<String, dynamic>? delivered;
  final Session session;
  final L10n t;
  final VoidCallback? onOpen;
  final void Function(String quantity)? onDeliver;

  @override
  Widget build(BuildContext context) {
    final row = delivered;
    final status = row?['status']?.toString();
    return Container(
      decoration: BoxDecoration(
        color: LactevaColors.milk,
        border: Border.all(color: LactevaColors.hairline),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Material(
        type: MaterialType.transparency,
        child: InkWell(
          onTap: onOpen,
          borderRadius: BorderRadius.circular(14),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            child: status == null
                ? _pending(context)
                : _settled(context, row!, status),
          ),
        ),
      ),
    );
  }

  Widget _pending(BuildContext context) {
    final deliver = onDeliver;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(child: _identity(bold: true)),
            const SizedBox(width: 12),
            _Chip(
              text: t.t('round.pending'),
              tint: LactevaColors.warningTint,
              ink: LactevaColors.onWarningTint,
            ),
          ],
        ),
        if (deliver != null) ...[
          const SizedBox(height: 12),
          _DeliverControls(t: t, onDeliver: deliver),
        ],
      ],
    );
  }

  Widget _settled(BuildContext context, Map<String, dynamic> row, String status) {
    final done = status == 'delivered';
    final quantity = row['quantity'];
    final unit = (row['quantity_unit'] ?? 'L').toString();
    return Row(
      children: [
        Icon(
          done ? Icons.check : Icons.error_outline,
          size: 20,
          color: done ? LactevaColors.success : LactevaColors.warning,
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                customer['name']?.toString() ?? '—',
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                  color: LactevaColors.ink,
                ),
              ),
              const SizedBox(height: 1),
              Text(
                // The status arrives as a CODE and is translated here. It used
                // to be printed raw, so a Hindi-speaking rider read the English
                // word the database happens to store (DEMO-016).
                '${customer['code'] ?? ''} · ${t.t('status.$status')}'
                '${quantity != null ? ' $quantity $unit' : ''}',
                style: const TextStyle(
                  fontSize: 12.5,
                  color: LactevaColors.muted,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 12),
        _outcomeChip(row, done),
      ],
    );
  }

  /// What happened to the money for this delivery.
  ///
  /// Three states, and each is a fact the platform sent. The board's third was
  /// "₹84 taken" — cash collected at the door — but nothing links a customer
  /// payment to a delivery, so a delivered row that is not yet on an invoice
  /// shows its VALUE and says it is still to be invoiced. Claiming money had
  /// changed hands would be the app inventing a receipt.
  Widget _outcomeChip(Map<String, dynamic> row, bool done) {
    if (!done) {
      return _Chip(
        text: t.t('round.retryLater'),
        tint: LactevaColors.warningTint,
        ink: LactevaColors.onWarningTint,
      );
    }
    if (row['invoice_id'] != null) {
      return _Chip(
        text: t.t('round.onInvoice'),
        tint: LactevaColors.waterTint,
        ink: LactevaColors.info,
      );
    }
    return _Chip(
      text: t.t('round.toInvoice', {'amount': money(row['amount']?.toString(), session)}),
      tint: LactevaColors.successTint,
      ink: LactevaColors.onSuccessTint,
    );
  }

  Widget _identity({required bool bold}) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        customer['name']?.toString() ?? '—',
        style: TextStyle(
          fontSize: 15,
          fontWeight: bold ? FontWeight.w700 : FontWeight.w600,
          color: LactevaColors.ink,
        ),
      ),
      const SizedBox(height: 1),
      Text(
        '${customer['code'] ?? ''} · ${t.t('round.notRecorded')}',
        style: const TextStyle(fontSize: 12.5, color: LactevaColors.muted),
      ),
    ],
  );
}

/// The stepper and the one tap beside it.
///
/// **It starts on the standing order and shows no number**, because the app
/// does not know one: the plan lives on the platform and an empty quantity is
/// the contract that means "whatever the plan says". Inventing 2.0 L to fill
/// the board's box would be the phone guessing at a household's order. The
/// first tap on `+` starts an override at half a litre; `−` walks it back and,
/// at the bottom, hands the decision back to the plan.
class _DeliverControls extends StatefulWidget {
  const _DeliverControls({required this.t, required this.onDeliver});

  final L10n t;
  final void Function(String quantity) onDeliver;

  @override
  State<_DeliverControls> createState() => _DeliverControlsState();
}

class _DeliverControlsState extends State<_DeliverControls> {
  /// Null means "the standing order" — not zero, which would be a delivery of
  /// nothing.
  double? _override;

  static const _step = 0.5;

  void _bump(double by) {
    setState(() {
      final next = (_override ?? 0) + by;
      _override = next <= 0 ? null : next;
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.t;
    final value = _override;
    return Row(
      children: [
        Container(
          decoration: BoxDecoration(
            border: Border.all(color: LactevaColors.controlBorder, width: 1.5),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              _StepButton(
                icon: Icons.remove,
                semantic: t.t('round.less'),
                onTap: value == null ? null : () => _bump(-_step),
              ),
              Container(
                width: 74,
                height: 46,
                alignment: Alignment.center,
                decoration: const BoxDecoration(
                  border: Border.symmetric(
                    vertical: BorderSide(
                      color: LactevaColors.controlBorder,
                      width: 1.5,
                    ),
                  ),
                ),
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(
                    value == null
                        ? t.t('round.standingOrder')
                        : '${value.toStringAsFixed(1)} L',
                    maxLines: 1,
                    style: TextStyle(
                      fontSize: value == null ? 13 : 17,
                      fontWeight: FontWeight.w700,
                      color: value == null
                          ? LactevaColors.muted
                          : LactevaColors.ink,
                    ),
                  ),
                ),
              ),
              _StepButton(
                icon: Icons.add,
                semantic: t.t('round.more'),
                onTap: () => _bump(_step),
              ),
            ],
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Material(
            color: LactevaColors.dairy,
            borderRadius: BorderRadius.circular(12),
            child: InkWell(
              borderRadius: BorderRadius.circular(12),
              onTap: () => widget.onDeliver(
                value == null ? '' : value.toStringAsFixed(1),
              ),
              child: SizedBox(
                height: 46,
                child: Center(
                  child: Text(
                    t.t('round.delivered'),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                      color: LactevaColors.onBrand,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _StepButton extends StatelessWidget {
  const _StepButton({
    required this.icon,
    required this.semantic,
    required this.onTap,
  });

  final IconData icon;
  final String semantic;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: semantic,
      child: InkWell(
        onTap: onTap,
        child: SizedBox(
          width: 46,
          height: 46,
          child: Icon(
            icon,
            size: 22,
            color: onTap == null
                ? LactevaColors.controlBorder
                : LactevaColors.dairy,
          ),
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.text, required this.tint, required this.ink});

  final String text;
  final Color tint;
  final Color ink;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
    decoration: BoxDecoration(
      color: tint,
      borderRadius: BorderRadius.circular(999),
    ),
    child: Text(
      text,
      style: TextStyle(
        fontSize: 11.5,
        fontWeight: FontWeight.w700,
        color: ink,
      ),
    ),
  );
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
              color: LactevaColors.success,
              onPressed: _busy ? null : () => _record('delivered'),
            ),
            const SizedBox(height: 12),
            _BigButton(
              label: t.t('record.notDelivered'),
              icon: Icons.cancel_outlined,
              color: LactevaColors.warning,
              onPressed: _busy ? null : () => _record('skipped'),
            ),
            const SizedBox(height: 12),
            _BigButton(
              label: t.t('record.returned'),
              icon: Icons.undo,
              color: Theme.of(context).colorScheme.outline,
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
