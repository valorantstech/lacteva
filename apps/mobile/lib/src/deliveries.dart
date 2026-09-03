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
    final groups = groupRound(_customers, _doneToday);
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
                            _RoundFigures(
                              report: _report!,
                              t: t,
                              session: widget.session,
                            ),
                          if (_customers.isEmpty)
                            _Empty(
                              icon: Icons.people_outline,
                              title: t.t('round.empty'),
                              detail: t.t('round.emptyDetail'),
                            )
                          else ...[
                            // WO-64: grouped by what has to be DONE about each
                            // stop, and the progress bar answers "how far
                            // through am I" without counting chips.
                            _RoundProgress(groups: groups, t: t),
                            for (final (key, rows) in <(String, List<Map<String, dynamic>>)>[
                              ('round.groupAttention', groups.attention),
                              ('round.groupToDo', groups.toDeliver),
                              ('round.groupDone', groups.delivered),
                            ])
                              if (rows.isNotEmpty) ...[
                                _GroupHeading(text: t.t(key), count: rows.length),
                                for (final c in rows)
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
                              ],
                          ],
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

/// The round, in the order a roundsman works it (WO-64).
///
/// The list was flat: twenty-four households in route order, delivered and
/// undelivered alike, so "what is left to do" was something the eye had to
/// compute from a column of chips. Grouped, the question is answered by the
/// shape of the screen.
///
/// Three groups, and the order is the argument:
///
///   NEEDS ATTENTION  a stop that came back or was skipped. Something went
///                    wrong and somebody has to decide; it goes first because
///                    it is the only part of the round that is not routine.
///   TO DELIVER       the work. Route order is preserved WITHIN the group —
///                    the sequence is the road, and reordering it would send
///                    a van back on itself.
///   DELIVERED        done, and last. Kept rather than hidden: a roundsman
///                    checking whether he has been somewhere needs to see it.
///
/// A pure function over rows the platform sent, so the ordering is testable
/// without a phone or a widget tree — like `inRouteOrder`, which it composes
/// rather than replaces.
class RoundGroups {
  const RoundGroups({
    required this.attention,
    required this.toDeliver,
    required this.delivered,
  });

  final List<Map<String, dynamic>> attention;
  final List<Map<String, dynamic>> toDeliver;
  final List<Map<String, dynamic>> delivered;

  /// How much of the round is behind them. `null` when there is nothing to
  /// do — a bar at 0% on an empty round would report a failure that is really
  /// an absence.
  double? get progress {
    final total = attention.length + toDeliver.length + delivered.length;
    return total == 0 ? null : delivered.length / total;
  }

  int get total => attention.length + toDeliver.length + delivered.length;
}

/// Split the round by what the roundsman must do about each stop.
///
/// `outcomes` is the map this screen already keeps: customer id → the row the
/// platform returned for today, or absent when nothing has been recorded.
RoundGroups groupRound(
  List<Map<String, dynamic>> customers,
  Map<String, Map<String, dynamic>> outcomes,
) {
  final attention = <Map<String, dynamic>>[];
  final toDeliver = <Map<String, dynamic>>[];
  final delivered = <Map<String, dynamic>>[];
  for (final customer in customers) {
    final row = outcomes[customer['id'].toString()];
    final status = (row?['status'] ?? '').toString();
    if (row == null) {
      toDeliver.add(customer);
    } else if (status == 'delivered') {
      delivered.add(customer);
    } else {
      // Skipped, returned, cancelled: an outcome exists and it is not a
      // delivery, so it is the part of the round somebody has to look at.
      attention.add(customer);
    }
  }
  return RoundGroups(
    attention: attention,
    toDeliver: toDeliver,
    delivered: delivered,
  );
}

/// How far through the round they are (WO-64).
///
/// The board said "0 / 14" and nothing else. A fraction is a fact a person has
/// to convert into a feeling; a bar IS the feeling, and the fraction stays
/// beside it because a roundsman counting stops needs the number too.
///
/// It is not an animation. A progress bar that fills over half a second is a
/// bar somebody watches instead of a round somebody works.
class _RoundProgress extends StatelessWidget {
  const _RoundProgress({required this.groups, required this.t});

  final RoundGroups groups;
  final L10n t;

  @override
  Widget build(BuildContext context) {
    final progress = groups.progress;
    if (progress == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: LinearProgressIndicator(
              value: progress,
              minHeight: 8,
              backgroundColor: LactevaColors.quietBar,
              valueColor: const AlwaysStoppedAnimation(LactevaColors.success),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            // The number stays: a bar answers "roughly how far", a count
            // answers "how many left", and a roundsman asks both.
            t.t('round.progress', {
              'done': '${groups.delivered.length}',
              'total': '${groups.total}',
            }),
            style: const TextStyle(fontSize: 12.5, color: LactevaColors.muted),
          ),
        ],
      ),
    );
  }
}

/// A group's name and size, so a heading is never a bare word.
class _GroupHeading extends StatelessWidget {
  const _GroupHeading({required this.text, required this.count});

  final String text;
  final int count;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 4, 20, 8),
      child: Row(
        children: [
          Text(
            text.toUpperCase(),
            style: const TextStyle(
              fontSize: 11.5,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.6,
              color: LactevaColors.muted,
            ),
          ),
          const SizedBox(width: 8),
          Text(
            '$count',
            style: const TextStyle(fontSize: 11.5, color: LactevaColors.muted),
          ),
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
  const _RoundFigures({required this.report, required this.t, required this.session});

  final Map<String, dynamic> report;
  final L10n t;

  /// WO-64: the organization's currency lives here, and money without it is
  /// not money. Passed in rather than looked up so this widget stays a pure
  /// render of what it was handed.
  final Session? session;

  @override
  Widget build(BuildContext context) {
    // WO-64: a dairy says "214.0 L", not "214.000 L", and a value without a
    // currency is not money — the WO-61 defect in a smaller font. Both figures
    // come from `format.dart` now, which is the one place that decides how a
    // number is said.
    final unit = (report['quantity_unit'] ?? 'L').toString();
    final cells = <(String, String)>[
      (
        quantity(report['planned_quantity'] ?? report['total_quantity'] ?? 0, unit: unit),
        t.t('round.toDeliver'),
      ),
      (
        '${count(report['deliveries'] ?? 0)} / '
            '${count(report['planned'] ?? report['customers_served'] ?? 0)}',
        t.t('round.done'),
      ),
      (money(report['total_amount'], session), t.t('round.value')),
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
            // WO-64: NOT YET is not a problem. This chip was amber, the same
            // amber a returned delivery wore, so at 5am every stop on the
            // round looked like a warning and the eye learned to skim them
            // all. It is the quietest ground in the palette now, and the
            // colour is spent on the rows that need a decision.
            _Chip(
              text: t.t('round.pending'),
              tint: LactevaColors.neutralTint,
              ink: LactevaColors.onNeutralTint,
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

  /// What follows from an outcome that is not a delivery, or nothing.
  String _consequence(String status) => switch (status) {
    'delivered' => '',
    'cancelled' => ' · ${t.t('round.recordedInError')}',
    // Skipped and returned are both milk the household is not invoiced for.
    _ => ' · ${t.t('round.notInvoiced')}',
  };

  Widget _settled(BuildContext context, Map<String, dynamic> row, String status) {
    final done = status == 'delivered';
    final delivered = row['quantity'];
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
                // WO-64: the quantity is said the way a dairy says it —
                // `20.0 L`, not the platform's stored `20.000 L` — and an
                // outcome that is not a delivery says what FOLLOWS from it
                // here, where there is width. The consequence is the
                // platform's own rule: `BILLABLE_STATUSES` is
                // `("delivered",)`, so nothing else is invoiced.
                '${customer['code'] ?? ''} · ${t.t('status.$status')}'
                '${_consequence(status)}'
                '${delivered != null ? ' · ${quantity(delivered, unit: unit)}' : ''}',
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
      // WO-64: an error must not look like a wait, and "Retry later" said
      // neither what happened nor what follows. Each outcome now names itself
      // and its consequence — and the consequence is the platform's own rule,
      // not a guess: `BILLABLE_STATUSES` is `("delivered",)`, so anything else
      // is milk the household is not charged for.
      final status = (row['status'] ?? '').toString();
      return switch (status) {
        // Milk came back. The one that costs the dairy something, and the
        // only outcome on this screen that gets the danger ground.
        'returned' => _Chip(
          text: t.t('round.returned'),
          tint: LactevaColors.dangerTint,
          ink: LactevaColors.onDangerTint,
        ),
        // Recorded in error: a correction, not a failure. Nothing to chase.
        'cancelled' => _Chip(
          text: t.t('round.cancelled'),
          tint: LactevaColors.neutralTint,
          ink: LactevaColors.onNeutralTint,
        ),
        // Customer away or declined — a real event worth seeing, worth
        // nothing to bill, and worth a call if it keeps happening.
        _ => _Chip(
          text: t.t('round.skipped'),
          tint: LactevaColors.warningTint,
          ink: LactevaColors.onWarningTint,
        ),
      };
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
