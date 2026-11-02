/// The delivery driver's day (P0-MOB-001 / P0-MOB-002 / WO-110).
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
/// * **The unit of work is a DELIVERY, not a stop (WO-110 §1).** A household
///   taking cow AND buffalo milk is two deliveries at one door. Walked on a
///   real handset, the old screen recorded one outcome per stop and counted
///   stops, so the second milk stayed scheduled at ₹0 every morning while
///   the run said "Every stop recorded". Now the stop lists every standing
///   order, "Delivered" records all of them (each adjustable, each skippable
///   on its own), a stop is done only when every delivery at it has an
///   outcome, and progress counts deliveries. The platform refuses to
///   complete a run with a scheduled delivery too — older APKs stay in the
///   field.
/// * **The Round tab is a home in every state (WO-110 §2)**: before the run
///   it says what to carry; during, the next door; after, the day's summary
///   with every stop reviewable and correctable until it is billed; and with
///   no run today, when the next one is.
library;

import 'package:flutter/material.dart';

import 'api.dart';
import 'l10n.dart';
import 'offline/offline_client.dart';
import 'session.dart';
import 'sign_out.dart';
import 'theme.dart';

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
  /// What comes after today (WO-110 §2), or null when nothing is known.
  Map<String, dynamic>? _next;
  bool _linked = true;
  bool _loading = true;
  String? _error;
  int _pending = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  /// Three calls for the whole screen: the profile (to tell the empty states
  /// apart), today's runs with their stops already on them, and what comes
  /// next — which is decoration, so its failure is nobody's problem.
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
      Map<String, dynamic>? next;
      if (linked) {
        try {
          next = await widget.client.myNextRound();
        } catch (_) {
          next = null;
        }
      }
      if (!mounted) return;
      setState(() {
        _linked = linked;
        _runs = runs;
        _next = next;
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

  void _say(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
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
      // The platform's refusal is the message — shown verbatim. WO-110 §1:
      // "2 of this run's deliveries are still scheduled — record them first:
      // B-204 BUFFALO-MILK …" is exactly what the delivery boy needs to read.
      _say(e.detail);
    } catch (_) {
      _say(t.t('driver.needsSignal'));
    }
  }

  /// One outcome for one delivery — the platform's narrow door, unchanged.
  /// Returns false when the platform refused or could not be reached.
  Future<bool> _recordOutcome(
    Map<String, dynamic> run,
    Map<String, dynamic> stop,
    String status, {
    String? notes,
    String? quantity,
    String? product,
  }) async {
    try {
      await widget.client.recordRunOutcomeOffline(
        runId: run['id'].toString(),
        customerId: stop['customer_id'].toString(),
        status: status,
        notes: notes,
        // WO-82 §1: an unchanged quantity sends nothing, exactly as before;
        // the product names which standing order when there are two.
        quantity: quantity,
        product: product,
      );
      return true;
    } on ApiException catch (e) {
      _say(e.detail);
      return false;
    } catch (_) {
      // Transport failure ≠ refusal (P0-PRODUCT-008 D-1).
      _say('Could not reach the platform');
      return false;
    }
  }

  /// Delivered, at the doorstep (WO-82 §1, WO-110 §1): the sheet lists EVERY
  /// delivery still open at this door, each prefilled with its standing
  /// figure and each skippable on its own — "took the cow, not the buffalo
  /// today". Confirming records every one of them; a quantity is sent only
  /// when the driver changed it, and the product whenever the household has
  /// more than one.
  Future<void> _deliver(Map<String, dynamic> run, Map<String, dynamic> stop) async {
    final t = L10n.of(widget.session);
    final orders = stopOrders(stop);
    if (orders.isEmpty) {
      // A stop the run could not describe: the platform still prices from
      // the plan, exactly as before WO-82.
      await _recordOutcome(run, stop, 'delivered');
      await _load();
      return;
    }
    final open = openOrders(stop);
    final choices = await showModalBottomSheet<List<_PourChoice>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: LactevaColors.cream,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => _DeliverySheet(orders: open, t: t),
    );
    if (choices == null || !mounted) return;
    for (final choice in choices) {
      final ok = await _recordOutcome(
        run,
        stop,
        choice.skipped ? 'skipped' : 'delivered',
        notes: choice.skipped ? t.t('driver.skippedDefaultNote') : null,
        quantity: choice.skipped || !choice.changed ? null : choice.quantity,
        product: orders.length > 1 ? choice.product : null,
      );
      if (!ok) break;
    }
    await _load();
  }

  /// Missed: every delivery still open at this door is skipped, with the
  /// note it always carried.
  Future<void> _missed(Map<String, dynamic> run, Map<String, dynamic> stop) async {
    final t = L10n.of(widget.session);
    final orders = stopOrders(stop);
    if (orders.isEmpty) {
      await _recordOutcome(run, stop, 'skipped', notes: t.t('driver.skippedDefaultNote'));
    } else {
      for (final order in openOrders(stop)) {
        final ok = await _recordOutcome(
          run,
          stop,
          'skipped',
          notes: t.t('driver.skippedDefaultNote'),
          product: orders.length > 1 ? '${order['product']}' : null,
        );
        if (!ok) break;
      }
    }
    await _load();
  }

  /// A correction from the door (WO-110 §2): one delivery, its quantity said
  /// again. The platform amends the recorded row — or refuses, in its own
  /// words, once a bill has taken it.
  Future<void> _correct(
    Map<String, dynamic> run,
    Map<String, dynamic> stop,
    Map<String, dynamic> order,
  ) async {
    final t = L10n.of(widget.session);
    final choices = await showModalBottomSheet<List<_PourChoice>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: LactevaColors.cream,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => _DeliverySheet(orders: [order], t: t, correcting: true),
    );
    if (choices == null || choices.isEmpty || !mounted) return;
    final choice = choices.single;
    await _recordOutcome(
      run,
      stop,
      choice.skipped ? 'skipped' : 'delivered',
      quantity: choice.skipped ? null : choice.quantity,
      product: stopOrders(stop).length > 1 ? choice.product : null,
    );
    await _load();
  }

  /// "Mark the rest as delivered" (WO-110 §4): one confirmation that states
  /// the count and what it does, then ONE queued operation. The platform
  /// marks every delivery of this run still scheduled at its standing
  /// quantity and leaves everything already recorded alone; a replay finds
  /// nothing scheduled and marks nothing.
  Future<void> _markRest(Map<String, dynamic> run) async {
    final t = L10n.of(widget.session);
    final remaining = deliveriesOf(runStops(run)).remaining;
    if (remaining == 0) return;
    final sure = await showDialog<bool>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: Text(t.t('driver.markRest')),
        content: Text(t.t('driver.markRestConfirm', {'count': remaining})),
        actions: [
          TextButton(
            key: const ValueKey('mark-rest-cancel'),
            onPressed: () => Navigator.of(dialog).pop(false),
            child: Text(t.t('common.cancel')),
          ),
          FilledButton(
            key: const ValueKey('mark-rest-confirm'),
            style: FilledButton.styleFrom(backgroundColor: LactevaColors.dairy),
            onPressed: () => Navigator.of(dialog).pop(true),
            child: Text(t.t('driver.markRestGo', {'count': remaining})),
          ),
        ],
      ),
    );
    if (sure != true || !mounted) return;
    try {
      final result = await widget.client.markRemainingDeliveredOffline(
        runId: run['id'].toString(),
      );
      final marked = result['marked'];
      _say(
        marked == null
            ? t.t('driver.markRestQueued', {'count': remaining})
            : t.t('driver.markRestDone', {'count': marked}),
      );
    } on ApiException catch (e) {
      _say(e.detail);
    } catch (_) {
      _say('Could not reach the platform');
    }
    await _load();
  }

  /// An item sold at the doorstep (WO-82 §2): the cached catalogue, a
  /// quantity, no price — the platform prices it, and a product with no
  /// price cannot be added at all.
  Future<void> _addItem(Map<String, dynamic> run, Map<String, dynamic> stop) async {
    final t = L10n.of(widget.session);
    List<Map<String, dynamic>> products;
    try {
      products = await widget.client.cachedProducts();
    } on ApiException catch (e) {
      _say(e.detail);
      return;
    } catch (_) {
      products = const [];
    }
    if (!mounted) return;
    final picked = await showModalBottomSheet<_ItemChoice>(
      context: context,
      isScrollControlled: true,
      backgroundColor: LactevaColors.cream,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => _ItemSheet(products: products, t: t),
    );
    if (picked == null || !mounted) return;
    try {
      await widget.client.recordSaleItemOffline(
        customerId: stop['customer_id'].toString(),
        productCode: picked.code,
        quantity: picked.quantity,
        saleDate: run['business_date']?.toString(),
      );
      if (!mounted) return;
      setState(() => _pending = widget.client.pendingCount);
      _say('${t.t('driver.itemAdded')}: ${picked.name} × ${picked.quantity}');
    } on ApiException catch (e) {
      _say(e.detail);
    } catch (_) {
      _say(t.t('driver.needsSignal'));
    }
  }

  void _review(Map<String, dynamic> run, Map<String, dynamic> stop) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => DriverStopReviewScreen(
          run: run,
          customerId: stop['customer_id'].toString(),
          client: widget.client,
          session: widget.session,
          onCorrect: (freshRun, freshStop, order) => _correct(freshRun, freshStop, order),
        ),
      ),
    );
  }

  /// The stop the driver is standing in front of, or null when the run is done.
  ///
  /// "Open" is the delivery domain's word: a stop is open while ANY delivery
  /// at it is still scheduled (WO-110 §1). Null and `scheduled` both mean
  /// nothing has been recorded yet.
  static Map<String, dynamic>? nextStop(List<Map<String, dynamic>> stops) {
    for (final stop in stops) {
      if (stopOpen(stop)) return stop;
    }
    return null;
  }

  static List<Map<String, dynamic>> openStops(List<Map<String, dynamic>> stops) =>
      stops.where(stopOpen).toList();

  @override
  Widget build(BuildContext context) {
    final t = L10n.of(widget.session);
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(
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
        client: widget.client,
        label: t.t('common.signOut'),
      );
    }
    if (_runs.isEmpty) {
      return RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: EdgeInsets.zero,
          children: [
            _Empty(
              icon: Icons.free_breakfast_outlined,
              title: t.t('driver.noRun'),
              detail: nextRoundLine(context, t, _next) ?? t.t('driver.noRunDetail'),
              client: widget.client,
              label: t.t('common.signOut'),
            ),
          ],
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: EdgeInsets.zero,
        children: [for (final run in _runs) _RunBoard(run: run, state: this)],
      ),
    );
  }
}

// --- the run, read as deliveries -------------------------------------------------------

/// The standing orders a run stop carries (WO-82 §1), as sent.
List<Map<String, dynamic>> stopOrders(Map<String, dynamic> stop) =>
    ((stop['orders'] as List?) ?? const []).cast<Map<String, dynamic>>();

List<Map<String, dynamic>> stopItems(Map<String, dynamic> stop) =>
    ((stop['items'] as List?) ?? const []).cast<Map<String, dynamic>>();

List<Map<String, dynamic>> runStops(Map<String, dynamic> run) =>
    ((run['stops'] as List?) ?? const []).cast<Map<String, dynamic>>();

bool _open(Object? status) => status == null || status == 'scheduled';

/// A delivery with no outcome yet.
bool orderOpen(Map<String, dynamic> order) => _open(order['delivery_status']);

/// The deliveries still open at a door. A stop the run could not describe
/// (no orders) is one delivery, judged by the stop's own status.
List<Map<String, dynamic>> openOrders(Map<String, dynamic> stop) =>
    stopOrders(stop).where(orderOpen).toList();

bool stopOpen(Map<String, dynamic> stop) {
  final orders = stopOrders(stop);
  if (orders.isEmpty) return _open(stop['delivery_status']);
  return orders.any(orderOpen);
}

/// Progress in DELIVERIES (WO-110 §1). The run says its own counts when it
/// can; a run that predates them is counted here from its stops' orders, a
/// stop without orders being one delivery.
class DeliveryCount {
  const DeliveryCount(this.done, this.total);
  final int done;
  final int total;
  int get remaining => total - done;
}

DeliveryCount deliveriesOf(List<Map<String, dynamic>> stops, {Map<String, dynamic>? run}) {
  final total = run?['deliveries_total'];
  final recorded = run?['deliveries_recorded'];
  if (total is int && recorded is int && total > 0) return DeliveryCount(recorded, total);
  var t = 0;
  var d = 0;
  for (final stop in stops) {
    final orders = stopOrders(stop);
    if (orders.isEmpty) {
      t += 1;
      if (!_open(stop['delivery_status'])) d += 1;
      continue;
    }
    t += orders.length;
    d += orders.where((o) => !orderOpen(o)).length;
  }
  return DeliveryCount(d, t);
}

/// Quantity per product across these orders, for "to carry" (standing, still
/// open) and "delivered" (what actually went). Keyed by product name and unit.
List<(String, String, double)> quantitiesByProduct(
  List<Map<String, dynamic>> stops, {
  required bool delivered,
}) {
  final sums = <String, double>{};
  final units = <String, String>{};
  for (final stop in stops) {
    for (final order in stopOrders(stop)) {
      final name = '${order['product_name'] ?? order['product']}';
      final unit = '${order['quantity_unit'] ?? 'L'}';
      double? value;
      if (delivered) {
        if (order['delivery_status'] != 'delivered') continue;
        value = double.tryParse('${order['quantity_delivered'] ?? order['quantity']}');
      } else {
        if (!orderOpen(order)) continue;
        value = double.tryParse('${order['quantity']}');
      }
      if (value == null) continue;
      sums[name] = (sums[name] ?? 0) + value;
      units[name] = unit;
    }
  }
  return [for (final e in sums.entries) (e.key, units[e.key]!, e.value)];
}

/// Items sold today across these stops, summed per product.
List<(String, String, double)> itemsSold(List<Map<String, dynamic>> stops) {
  final sums = <String, double>{};
  final units = <String, String>{};
  for (final stop in stops) {
    for (final item in stopItems(stop)) {
      final name = '${item['product_name'] ?? item['product']}';
      final value = double.tryParse('${item['quantity']}') ?? 0;
      sums[name] = (sums[name] ?? 0) + value;
      units[name] = '${item['unit'] ?? 'pc'}';
    }
  }
  return [for (final e in sums.entries) (e.key, units[e.key]!, e.value)];
}

/// A stop nothing was delivered at.
bool stopSkipped(Map<String, dynamic> stop) {
  final orders = stopOrders(stop);
  if (orders.isEmpty) return stop['delivery_status'] == 'skipped';
  return orders.isNotEmpty &&
      orders.every((o) => !orderOpen(o)) &&
      orders.every((o) => o['delivery_status'] != 'delivered');
}

/// A quantity the way the day summary prints it: whole numbers plain,
/// fractions to three places without trailing zeros.
String tidy(double value) {
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  var s = value.toStringAsFixed(3);
  while (s.endsWith('0')) {
    s = s.substring(0, s.length - 1);
  }
  return s;
}

/// "Next round: Mon, Sep 28 · 2 stops", or "Tomorrow: 2 stops" when that is
/// what it is — from the platform's own answer, localized by Flutter's date
/// formatter rather than a table of month names.
String? nextRoundLine(BuildContext context, L10n t, Map<String, dynamic>? next) {
  final iso = next?['business_date'];
  if (iso == null) return null;
  final day = DateTime.tryParse('$iso');
  if (day == null) return null;
  final stops = (next?['stops'] as num?)?.toInt() ?? 0;
  final today = DateTime.now();
  final tomorrow = DateTime(today.year, today.month, today.day + 1);
  if (day.year == tomorrow.year && day.month == tomorrow.month && day.day == tomorrow.day) {
    return t.t('driver.tomorrow', {'count': stops});
  }
  final when = MaterialLocalizations.of(context).formatMediumDate(day);
  return t.t('driver.nextRound', {'date': when, 'count': stops});
}

/// One run, as the Driver board draws it — a home in every state.
class _RunBoard extends StatelessWidget {
  const _RunBoard({required this.run, required this.state});

  final Map<String, dynamic> run;
  final _DriverHomeScreenState state;

  @override
  Widget build(BuildContext context) {
    final t = L10n.of(state.widget.session);
    final status = (run['status'] ?? '').toString();
    final stops = runStops(run);
    final count = deliveriesOf(stops, run: run);
    final open = _DriverHomeScreenState.openStops(stops);
    final next = _DriverHomeScreenState.nextStop(stops);
    final finished = status == 'completed' || status == 'cancelled';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _RunHeader(run: run, count: count, t: t),
        if (status == 'planned') ...[
          _ToCarry(stops: stops, t: t),
          _ThenList(stops: stops, t: t, labelKey: 'driver.todaysStops'),
        ],
        if (status == 'in_progress' && next != null)
          _NextStopCard(
            run: run,
            stop: next,
            position: stops.length - open.length + 1,
            total: stops.length,
            state: state,
            t: t,
          ),
        if (status == 'in_progress' && open.length > 1)
          _ThenList(stops: open.skip(1).toList(), t: t),
        if (status == 'in_progress' && count.remaining > 0)
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
            child: SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                key: const ValueKey('mark-rest'),
                onPressed: () => state._markRest(run),
                icon: const Icon(Icons.done_all, size: 18),
                label: Text(t.t('driver.markRest')),
              ),
            ),
          ),
        if (finished) ...[
          _DaySummary(run: run, stops: stops, next: state._next, t: t),
          _TodaysStops(run: run, stops: stops, state: state, t: t),
        ],
        _OnBoardBand(run: run, count: count, state: state, t: t),
      ],
    );
  }
}

/// Which round this is, and how much of it is left — in deliveries.
class _RunHeader extends StatelessWidget {
  const _RunHeader({required this.run, required this.count, required this.t});

  final Map<String, dynamic> run;
  final DeliveryCount count;
  final L10n t;

  @override
  Widget build(BuildContext context) {
    final slot = (run['slot'] ?? '').toString();
    final route = (run['route_name'] ?? run['route_code'] ?? '').toString();

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // WO-96 / D-45: a Wrap, not a Row — at system text scale 2.0 on a
          // 320px phone the state pill no longer fits beside the title and
          // falls below it instead of overflowing the edge.
          Wrap(
            spacing: 8,
            runSpacing: 4,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(
                t.t('driver.roundTitle', {'slot': t.t('slot.$slot')}),
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.44,
                  color: LactevaColors.ink,
                ),
              ),
              // The chip says the STATE, not a wall-clock time: `started_at`
              // is a UTC instant and this app does no timezone arithmetic.
              _Pill(
                text: t.t('driver.status.${run['status']}'),
                tint: LactevaColors.successTint,
                ink: LactevaColors.onSuccessTint,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: Text(
                  route,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 13,
                    color: LactevaColors.muted,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              // Flexible: "2 of 4 deliveries" at text scale 2.0 must shrink
              // the route name, not run off the phone (WO-96 / D-45).
              Flexible(
                child: Text(
                  t.t('driver.ofDeliveries', {'done': count.done, 'total': count.total}),
                  textAlign: TextAlign.end,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: LactevaColors.ink,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 7),
          _ProgressBar(done: count.done, total: count.total),
        ],
      ),
    );
  }
}

class _ProgressBar extends StatelessWidget {
  const _ProgressBar({required this.done, required this.total});

  final int done;
  final int total;

  @override
  Widget build(BuildContext context) {
    final fraction = total == 0 ? 0.0 : (done / total).clamp(0.0, 1.0);
    return Semantics(
      value: '$done / $total',
      child: ClipRRect(
        borderRadius: BorderRadius.circular(999),
        child: SizedBox(
          height: 10,
          child: Stack(
            children: [
              const ColoredBox(
                color: LactevaColors.hairline,
                child: SizedBox.expand(),
              ),
              FractionallySizedBox(
                widthFactor: fraction,
                child: const DecoratedBox(
                  decoration: BoxDecoration(gradient: kProgressGradient),
                  child: SizedBox.expand(),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Before the run: what to load, per product (WO-110 §2).
class _ToCarry extends StatelessWidget {
  const _ToCarry({required this.stops, required this.t});

  final List<Map<String, dynamic>> stops;
  final L10n t;

  @override
  Widget build(BuildContext context) {
    final rows = quantitiesByProduct(stops, delivered: false);
    if (rows.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 4),
      child: _Panel(
        label: t.t('driver.toCarry'),
        children: [
          for (final (name, unit, value) in rows)
            _FigureRow(key: ValueKey('carry-$name'), label: name, figure: '${tidy(value)} $unit'),
        ],
      ),
    );
  }
}

/// After the run: the day, in figures a delivery boy recognises (WO-110 §2).
class _DaySummary extends StatelessWidget {
  const _DaySummary({
    required this.run,
    required this.stops,
    required this.next,
    required this.t,
  });

  final Map<String, dynamic> run;
  final List<Map<String, dynamic>> stops;
  final Map<String, dynamic>? next;
  final L10n t;

  @override
  Widget build(BuildContext context) {
    final delivered = quantitiesByProduct(stops, delivered: true);
    final sold = itemsSold(stops);
    final skipped = stops.where(stopSkipped).length;
    final nextLine = nextRoundLine(context, t, next);
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 4),
      child: _Panel(
        label: t.t('driver.daySummary'),
        children: [
          if (delivered.isEmpty)
            Text(t.t('driver.nothingDelivered'), style: const TextStyle(color: LactevaColors.muted)),
          for (final (name, unit, value) in delivered)
            _FigureRow(
              key: ValueKey('delivered-$name'),
              label: '${t.t('driver.outcome.delivered')} · $name',
              figure: '${tidy(value)} $unit',
            ),
          for (final (name, unit, value) in sold)
            _FigureRow(
              key: ValueKey('sold-$name'),
              label: '${t.t('driver.itemsSold')} · $name',
              figure: '${tidy(value)} $unit',
            ),
          _FigureRow(
            key: const ValueKey('skipped-count'),
            label: t.t('driver.stopsSkipped'),
            figure: '$skipped',
          ),
          if (nextLine != null) ...[
            const SizedBox(height: 6),
            Text(
              nextLine,
              key: const ValueKey('next-round'),
              style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: LactevaColors.ink),
            ),
          ],
        ],
      ),
    );
  }
}

/// After the run: every stop of the day, openable to review and correct.
class _TodaysStops extends StatelessWidget {
  const _TodaysStops({
    required this.run,
    required this.stops,
    required this.state,
    required this.t,
  });

  final Map<String, dynamic> run;
  final List<Map<String, dynamic>> stops;
  final _DriverHomeScreenState state;
  final L10n t;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionLabel(text: t.t('driver.todaysStops')),
          const SizedBox(height: 10),
          for (final stop in stops)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: InkWell(
                key: ValueKey('review-${stop['customer_id']}'),
                borderRadius: BorderRadius.circular(14),
                onTap: () => state._review(run, stop),
                child: _ThenRow(stop: stop, dimmed: false, trailing: const Icon(Icons.chevron_right, color: LactevaColors.muted)),
              ),
            ),
        ],
      ),
    );
  }
}

/// A panel of figures under a section label.
class _Panel extends StatelessWidget {
  const _Panel({required this.label, required this.children});
  final String label;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      _SectionLabel(text: label),
      const SizedBox(height: 10),
      Container(
        width: double.infinity,
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        decoration: BoxDecoration(
          color: LactevaColors.milk,
          border: Border.all(color: LactevaColors.hairline),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
      ),
      const SizedBox(height: 12),
    ],
  );
}

class _FigureRow extends StatelessWidget {
  const _FigureRow({super.key, required this.label, required this.figure});
  final String label;
  final String figure;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Row(
      children: [
        Expanded(
          child: Text(label, style: const TextStyle(fontSize: 14, color: LactevaColors.ink)),
        ),
        const SizedBox(width: 12),
        Text(
          figure,
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: LactevaColors.ink),
        ),
      ],
    ),
  );
}

/// The one stop that matters, at the size it matters.
///
/// Glanceability is the constraint: a driver reads this through a windscreen
/// with the engine running. The run describes itself: each stop carries its
/// standing order(s) — product name, quantity, unit — resolved server-side
/// from the plan (WO-82 §1), so the card says what to pour, EACH milk on its
/// own line with its own state (WO-110 §1), and "Delivered" opens every open
/// figure to be changed or skipped at the doorstep. The big figure stays the
/// stop's position — the thing a driver checks against a paper list.
class _NextStopCard extends StatelessWidget {
  const _NextStopCard({
    required this.run,
    required this.stop,
    required this.position,
    required this.total,
    required this.state,
    required this.t,
  });

  final Map<String, dynamic> run;
  final Map<String, dynamic> stop;
  final int position;
  final int total;
  final _DriverHomeScreenState state;
  final L10n t;

  @override
  Widget build(BuildContext context) {
    final address = (stop['address'] ?? '').toString();
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionLabel(text: t.t('driver.nextStop')),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: LactevaColors.milk,
              borderRadius: BorderRadius.circular(18),
              boxShadow: [
                BoxShadow(
                  color: LactevaColors.ink.withValues(alpha: 0.06),
                  blurRadius: 6,
                  offset: const Offset(0, 2),
                ),
                BoxShadow(
                  color: LactevaColors.dairy.withValues(alpha: 0.10),
                  blurRadius: 28,
                  offset: const Offset(0, 12),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${stop['name']}',
                            style: const TextStyle(
                              fontSize: 20,
                              fontWeight: FontWeight.w700,
                              letterSpacing: -0.2,
                              color: LactevaColors.ink,
                            ),
                          ),
                          if (address.isNotEmpty) ...[
                            const SizedBox(height: 3),
                            Text(
                              address,
                              style: const TextStyle(
                                fontSize: 13.5,
                                color: LactevaColors.muted,
                              ),
                            ),
                          ],
                          // WO-82 §1 / WO-110 §1: what to pour, from the run
                          // itself — every milk, each with its own state.
                          for (final order in stopOrders(stop)) ...[
                            const SizedBox(height: 6),
                            _OrderLine(order: order, t: t),
                          ],
                        ],
                      ),
                    ),
                    const SizedBox(width: 12),
                    Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        color: LactevaColors.waterTint,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Icon(
                        Icons.place_outlined,
                        size: 22,
                        color: LactevaColors.water,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Flexible(
                      child: FittedBox(
                        fit: BoxFit.scaleDown,
                        alignment: AlignmentDirectional.centerStart,
                        child: Text(
                          t.t('driver.stopNumber', {'n': position}),
                          maxLines: 1,
                          style: const TextStyle(
                            fontSize: 40,
                            fontWeight: FontWeight.w700,
                            letterSpacing: -0.8,
                            color: LactevaColors.ink,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Flexible(
                      child: Padding(
                        padding: const EdgeInsets.only(bottom: 4),
                        child: Text(
                          t.t('driver.ofTotalStops', {'total': total}),
                          style: const TextStyle(
                            fontSize: 14,
                            color: LactevaColors.muted,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      flex: 16,
                      child: _Action(
                        key: const ValueKey('stop-delivered'),
                        label: t.t('driver.outcome.delivered'),
                        icon: Icons.check,
                        primary: true,
                        onTap: () => state._deliver(run, stop),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      flex: 10,
                      child: _Action(
                        key: const ValueKey('stop-missed'),
                        label: t.t('driver.missed'),
                        primary: false,
                        onTap: () => state._missed(run, stop),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                // WO-82 §2: a thing sold beside the milk.
                Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: TextButton.icon(
                    key: const ValueKey('stop-add-item'),
                    onPressed: () => state._addItem(run, stop),
                    icon: const Icon(Icons.shopping_bag_outlined, size: 18),
                    label: Text(t.t('driver.addItem')),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// One standing order at a door: "Cow milk · 1.000 L", and its state once
/// something has been recorded — so a household with two milks shows which
/// one is still to be poured.
class _OrderLine extends StatelessWidget {
  const _OrderLine({required this.order, required this.t});
  final Map<String, dynamic> order;
  final L10n t;

  @override
  Widget build(BuildContext context) {
    final status = order['delivery_status'];
    final recorded = !_open(status);
    return Row(
      children: [
        Expanded(
          child: Text(
            '${order['product_name'] ?? order['product']} · '
            '${order['quantity']} ${order['quantity_unit'] ?? 'L'}',
            key: ValueKey('stop-order-${order['product']}'),
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w600,
              color: recorded ? LactevaColors.muted : LactevaColors.ink,
              decoration: recorded ? TextDecoration.lineThrough : null,
            ),
          ),
        ),
        if (recorded) ...[
          const SizedBox(width: 8),
          _Pill(
            text: t.t('driver.outcome.$status'),
            tint: status == 'delivered' ? LactevaColors.successTint : LactevaColors.hairline,
            ink: status == 'delivered' ? LactevaColors.onSuccessTint : LactevaColors.muted,
          ),
        ],
      ],
    );
  }
}

/// The step a ± button moves a quantity by: a quarter for a measured
/// product, one for a counted one.
double stepFor(String unit) => unit == 'pc' ? 1.0 : 0.25;

/// A quantity as the platform wants it: three decimals, never negative.
String formatQuantity(double value) =>
    (value < 0 ? 0.0 : value).toStringAsFixed(3);

class _PourChoice {
  const _PourChoice({
    required this.product,
    required this.quantity,
    required this.changed,
    this.skipped = false,
  });
  final String product;
  final String quantity;
  final bool changed;
  final bool skipped;
}

/// How much did you pour? (WO-82 §1, WO-110 §1). EVERY open delivery at the
/// door, each prefilled with its standing figure, big digits, one hand: ±
/// buttons for the unit's step and a number pad behind the field, and "Not
/// today" per milk. Confirming with a figure untouched sends no quantity for
/// it — "yes, the usual" must stay one tap.
class _DeliverySheet extends StatefulWidget {
  const _DeliverySheet({required this.orders, required this.t, this.correcting = false});
  final List<Map<String, dynamic>> orders;
  final L10n t;
  final bool correcting;
  @override
  State<_DeliverySheet> createState() => _DeliverySheetState();
}

class _DeliverySheetState extends State<_DeliverySheet> {
  late final List<TextEditingController> _fields = [
    for (final order in widget.orders) TextEditingController(text: _standing(order)),
  ];
  late final List<bool> _skipped = List.filled(widget.orders.length, false);

  String _unit(Map<String, dynamic> order) => (order['quantity_unit'] ?? 'L').toString();
  String _standing(Map<String, dynamic> order) => formatQuantity(
    double.tryParse('${widget.correcting ? (order['quantity_delivered'] ?? order['quantity']) : order['quantity']}') ?? 0,
  );

  void _nudge(int i, double delta) {
    final current = double.tryParse(_fields[i].text.trim()) ?? 0;
    _fields[i].text = formatQuantity(current + delta);
    setState(() {});
  }

  @override
  void dispose() {
    for (final f in _fields) {
      f.dispose();
    }
    super.dispose();
  }

  bool get _valid {
    for (var i = 0; i < widget.orders.length; i++) {
      if (_skipped[i]) continue;
      final typed = double.tryParse(_fields[i].text.trim());
      if (typed == null || typed <= 0) return false;
    }
    return true;
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.t;
    final bottom = MediaQuery.viewInsetsOf(context).bottom;
    final several = widget.orders.length > 1;
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 16, 20, 20 + bottom),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              t.t(widget.correcting ? 'driver.correctTitle' : 'driver.quantityTitle'),
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: LactevaColors.ink),
            ),
            for (var i = 0; i < widget.orders.length; i++) ...[
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      several
                          ? '${widget.orders[i]['product_name'] ?? widget.orders[i]['product']} · '
                              '${t.t('driver.pours')}: ${_standing(widget.orders[i])} ${_unit(widget.orders[i])}'
                          : '${t.t('driver.pours')}: ${_standing(widget.orders[i])} ${_unit(widget.orders[i])}',
                      key: ValueKey('pour-${widget.orders[i]['product']}'),
                      style: const TextStyle(fontSize: 13.5, color: LactevaColors.muted),
                    ),
                  ),
                  if (!widget.correcting)
                    TextButton(
                      key: ValueKey('pour-skip-${widget.orders[i]['product']}'),
                      onPressed: () => setState(() => _skipped[i] = !_skipped[i]),
                      child: Text(_skipped[i] ? t.t('driver.undoSkip') : t.t('driver.skipThis')),
                    ),
                ],
              ),
              if (_skipped[i])
                Text(
                  t.t('driver.skippedToday'),
                  key: ValueKey('pour-skipped-${widget.orders[i]['product']}'),
                  style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: LactevaColors.muted),
                )
              else ...[
                const SizedBox(height: 8),
                Row(
                  children: [
                    _StepButton(
                      key: ValueKey(several ? 'pour-minus-${widget.orders[i]['product']}' : 'pour-minus'),
                      label: '−',
                      onTap: () => _nudge(i, -stepFor(_unit(widget.orders[i]))),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: TextField(
                        key: ValueKey(several ? 'pour-quantity-${widget.orders[i]['product']}' : 'pour-quantity'),
                        controller: _fields[i],
                        textAlign: TextAlign.center,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        style: TextStyle(
                          fontSize: several ? 32 : 40,
                          fontWeight: FontWeight.w700,
                          color: LactevaColors.ink,
                        ),
                        decoration: InputDecoration(
                          suffixText: _unit(widget.orders[i]),
                          border: const OutlineInputBorder(),
                        ),
                        onChanged: (_) => setState(() {}),
                      ),
                    ),
                    const SizedBox(width: 10),
                    _StepButton(
                      key: ValueKey(several ? 'pour-plus-${widget.orders[i]['product']}' : 'pour-plus'),
                      label: '+',
                      onTap: () => _nudge(i, stepFor(_unit(widget.orders[i]))),
                    ),
                  ],
                ),
              ],
            ],
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              height: 56,
              child: FilledButton(
                key: const ValueKey('pour-confirm'),
                style: FilledButton.styleFrom(backgroundColor: LactevaColors.dairy),
                onPressed: !_valid
                    ? null
                    : () {
                        final choices = <_PourChoice>[];
                        for (var i = 0; i < widget.orders.length; i++) {
                          final order = widget.orders[i];
                          if (_skipped[i]) {
                            choices.add(_PourChoice(
                              product: '${order['product']}',
                              quantity: _standing(order),
                              changed: false,
                              skipped: true,
                            ));
                            continue;
                          }
                          final quantity = formatQuantity(double.parse(_fields[i].text.trim()));
                          choices.add(_PourChoice(
                            product: '${order['product']}',
                            quantity: quantity,
                            changed: quantity != _standing(order),
                          ));
                        }
                        Navigator.of(context).pop(choices);
                      },
                child: Text(t.t(widget.correcting ? 'driver.confirmCorrection' : 'driver.confirmDelivered')),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StepButton extends StatelessWidget {
  const _StepButton({super.key, required this.label, required this.onTap});
  final String label;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => SizedBox(
    width: 56,
    height: 56,
    child: OutlinedButton(
      onPressed: onTap,
      child: Text(label, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
    ),
  );
}

class _ItemChoice {
  const _ItemChoice({required this.code, required this.name, required this.quantity});
  final String code;
  final String name;
  final String quantity;
}

/// Add an item (WO-82 §2): the cached catalogue, a quantity, no price. A
/// product with no default price is shown but cannot be added — the platform
/// would refuse a zero-rupee line and the app says why first.
class _ItemSheet extends StatefulWidget {
  const _ItemSheet({required this.products, required this.t});
  final List<Map<String, dynamic>> products;
  final L10n t;
  @override
  State<_ItemSheet> createState() => _ItemSheetState();
}

class _ItemSheetState extends State<_ItemSheet> {
  Map<String, dynamic>? _picked;
  double _quantity = 1;

  @override
  Widget build(BuildContext context) {
    final t = widget.t;
    final bottom = MediaQuery.viewInsetsOf(context).bottom;
    final picked = _picked;
    final step = picked == null ? 1.0 : stepFor((picked['unit'] ?? 'pc').toString());
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 16, 20, 20 + bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            t.t('driver.itemTitle'),
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: LactevaColors.ink),
          ),
          const SizedBox(height: 10),
          if (widget.products.isEmpty)
            Text(t.t('driver.noCatalogue'), style: const TextStyle(color: LactevaColors.muted))
          else
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 280),
              child: ListView(
                shrinkWrap: true,
                children: [
                  for (final product in widget.products)
                    ListTile(
                      key: ValueKey('item-${product['code']}'),
                      dense: true,
                      selected: identical(product, picked),
                      enabled: product['default_price'] != null,
                      title: Text('${product['name']}'),
                      subtitle: Text(
                        product['default_price'] == null
                            ? t.t('driver.itemNoPrice')
                            : '${product['default_price']} / ${product['unit']}',
                      ),
                      onTap: product['default_price'] == null
                          ? null
                          : () => setState(() {
                              _picked = product;
                              _quantity = 1;
                            }),
                    ),
                ],
              ),
            ),
          if (picked != null) ...[
            const SizedBox(height: 12),
            Text(t.t('driver.itemQuantity'), style: const TextStyle(color: LactevaColors.muted)),
            const SizedBox(height: 6),
            Row(
              children: [
                _StepButton(
                  key: const ValueKey('item-minus'),
                  label: '−',
                  onTap: () => setState(() => _quantity = (_quantity - step).clamp(step, 999)),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    '${step == 1.0 ? _quantity.toStringAsFixed(0) : formatQuantity(_quantity)} ${picked['unit']}',
                    key: const ValueKey('item-quantity'),
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 32, fontWeight: FontWeight.w700, color: LactevaColors.ink),
                  ),
                ),
                const SizedBox(width: 10),
                _StepButton(
                  key: const ValueKey('item-plus'),
                  label: '+',
                  onTap: () => setState(() => _quantity += step),
                ),
              ],
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              height: 56,
              child: FilledButton(
                key: const ValueKey('item-confirm'),
                style: FilledButton.styleFrom(backgroundColor: LactevaColors.dairy),
                onPressed: () => Navigator.of(context).pop(
                  _ItemChoice(
                    code: '${picked['code']}',
                    name: '${picked['name']}',
                    quantity: formatQuantity(_quantity),
                  ),
                ),
                child: Text(t.t('driver.addItem')),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// 56dp, because the hands work here.
class _Action extends StatelessWidget {
  const _Action({
    super.key,
    required this.label,
    required this.primary,
    required this.onTap,
    this.icon,
  });

  final String label;
  final bool primary;
  final VoidCallback onTap;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final glyph = icon;
    return Material(
      color: primary ? LactevaColors.dairy : LactevaColors.milk,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Ink(
          decoration: BoxDecoration(
            color: primary ? LactevaColors.dairy : LactevaColors.milk,
            borderRadius: BorderRadius.circular(14),
            border: primary
                ? null
                : Border.all(color: LactevaColors.controlBorder, width: 1.5),
          ),
          child: SizedBox(
            height: LactevaMetrics.primaryActionHeight,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (glyph != null) ...[
                  Icon(glyph, size: 20, color: LactevaColors.onBrand),
                  const SizedBox(width: 9),
                ],
                Flexible(
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: primary ? 16.5 : 15.5,
                      fontWeight: primary
                          ? FontWeight.w700
                          : FontWeight.w600,
                      color: primary
                          ? LactevaColors.onBrand
                          : LactevaColors.ink,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// What comes after the one in hand — or, before the run, the whole round.
class _ThenList extends StatelessWidget {
  const _ThenList({required this.stops, required this.t, this.labelKey = 'driver.then'});

  final List<Map<String, dynamic>> stops;
  final L10n t;
  final String labelKey;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionLabel(text: t.t(labelKey)),
          const SizedBox(height: 10),
          for (var i = 0; i < stops.length; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Opacity(
                // The board dims the far end of the queue: the third stop
                // away is context, not work.
                opacity: labelKey == 'driver.then' && i >= 2 ? 0.65 : 1,
                child: _ThenRow(stop: stops[i], dimmed: labelKey == 'driver.then' && i >= 2),
              ),
            ),
        ],
      ),
    );
  }
}

class _ThenRow extends StatelessWidget {
  const _ThenRow({required this.stop, required this.dimmed, this.trailing});

  final Map<String, dynamic> stop;
  final bool dimmed;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final address = (stop['address'] ?? '').toString();
    final orders = stopOrders(stop);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
      decoration: BoxDecoration(
        color: LactevaColors.milk,
        border: Border.all(color: LactevaColors.hairline),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          Container(
            width: 26,
            height: 26,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: dimmed
                  ? LactevaColors.hairline
                  : LactevaColors.successTint,
            ),
            child: Text(
              '${stop['position']}',
              style: TextStyle(
                fontSize: 12.5,
                fontWeight: FontWeight.w700,
                color: dimmed ? LactevaColors.muted : LactevaColors.dairy,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${stop['name']}',
                  style: const TextStyle(
                    fontSize: 14.5,
                    fontWeight: FontWeight.w600,
                    color: LactevaColors.ink,
                  ),
                ),
                if (address.isNotEmpty)
                  Text(
                    address,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 13,
                      color: LactevaColors.muted,
                    ),
                  ),
                // WO-110 §1: a household with two milks says so in the queue.
                if (orders.isNotEmpty)
                  Text(
                    orders
                        .map((o) => '${o['product_name'] ?? o['product']} ${o['quantity']} ${o['quantity_unit'] ?? 'L'}')
                        .join(' · '),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12.5, color: LactevaColors.muted),
                  ),
              ],
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

/// The van, and the way off it.
///
/// Dark because it is a FACT rather than a control — the eye passes over it
/// unless it is looking. The action is the run transition the platform will
/// actually accept: Start before the run begins, End once every DELIVERY is
/// recorded (WO-110 §1) — and the platform refuses End otherwise, naming the
/// deliveries, which this band shows verbatim.
class _OnBoardBand extends StatelessWidget {
  const _OnBoardBand({
    required this.run,
    required this.count,
    required this.state,
    required this.t,
  });

  final Map<String, dynamic> run;
  final DeliveryCount count;
  final _DriverHomeScreenState state;
  final L10n t;

  @override
  Widget build(BuildContext context) {
    final status = (run['status'] ?? '').toString();
    final planned = status == 'planned';
    final remaining = count.remaining;
    final canEnd = status == 'in_progress' && remaining == 0;
    final label = planned
        ? t.t('driver.start')
        : canEnd
        ? t.t('driver.complete')
        : null;

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 6, 20, 26),
      child: Material(
        color: LactevaColors.ink,
        borderRadius: BorderRadius.circular(16),
        child: InkWell(
          onTap: label == null
              ? null
              : () => state._transition(run['id'].toString(), planned),
          borderRadius: BorderRadius.circular(16),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
            child: Row(
              children: [
                const Icon(
                  Icons.water_drop_outlined,
                  size: 20,
                  color: LactevaColors.onBrandLive,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        (run['vehicle_registration'] ?? '').toString().isEmpty
                            ? '${run['route_name'] ?? run['route_code'] ?? ''}'
                            : run['vehicle_registration'].toString(),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: LactevaColors.onInk,
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      Text(
                        remaining == 0
                            ? t.t('driver.everyDeliveryRecorded')
                            : t.t('driver.remaining', {'count': remaining}),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: LactevaColors.onInkMuted,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
                if (label != null) ...[
                  const SizedBox(width: 12),
                  Text(
                    label,
                    style: const TextStyle(
                      color: LactevaColors.onBrandLive,
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// One stop of a finished (or running) round, opened to review — every
/// delivery with what was recorded, and "Correct" until a bill has taken it
/// (WO-110 §2). Pushed, so the app bar's back arrow and Android's back button
/// both return to the Round tab.
class DriverStopReviewScreen extends StatefulWidget {
  const DriverStopReviewScreen({
    super.key,
    required this.run,
    required this.customerId,
    required this.client,
    required this.session,
    required this.onCorrect,
  });

  final Map<String, dynamic> run;
  final String customerId;
  final OfflineApiClient client;
  final Session session;
  final Future<void> Function(
    Map<String, dynamic> run,
    Map<String, dynamic> stop,
    Map<String, dynamic> order,
  ) onCorrect;

  @override
  State<DriverStopReviewScreen> createState() => _DriverStopReviewScreenState();
}

class _DriverStopReviewScreenState extends State<DriverStopReviewScreen> {
  late Map<String, dynamic> _run = widget.run;

  Map<String, dynamic>? get _stop {
    for (final stop in runStops(_run)) {
      if (stop['customer_id'].toString() == widget.customerId) return stop;
    }
    return null;
  }

  /// After a correction, the run is read again so the screen shows the
  /// platform's answer rather than the phone's assumption.
  Future<void> _refresh() async {
    try {
      final runs = await widget.client.myRuns();
      final fresh = runs.where((r) => r['id'].toString() == _run['id'].toString());
      if (fresh.isNotEmpty && mounted) setState(() => _run = fresh.first);
    } catch (_) {
      // Offline: what was shown stays; the correction is in the queue.
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = L10n.of(widget.session);
    final stop = _stop;
    final cancelled = _run['status'] == 'cancelled';
    return Scaffold(
      appBar: AppBar(
        // The explicit arrow: a driver could not find the way back (WO-110 §2).
        leading: BackButton(key: const ValueKey('review-back')),
        title: Text(stop == null ? t.t('driver.review') : '${stop['name']}'),
      ),
      body: stop == null
          ? Center(child: Text(t.t('driver.review')))
          : ListView(
              padding: const EdgeInsets.all(20),
              children: [
                if ('${stop['address'] ?? ''}'.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text('${stop['address']}', style: const TextStyle(color: LactevaColors.muted)),
                  ),
                _SectionLabel(text: t.t('driver.deliveries')),
                const SizedBox(height: 10),
                for (final order in stopOrders(stop))
                  _ReviewRow(
                    order: order,
                    t: t,
                    onCorrect: cancelled || order['invoiced'] == true || orderOpen(order)
                        ? null
                        : () async {
                            await widget.onCorrect(_run, stop, order);
                            await _refresh();
                          },
                  ),
                if (stopOrders(stop).isEmpty)
                  Text(
                    t.t('driver.outcome.${stop['delivery_status'] ?? 'scheduled'}'),
                    style: const TextStyle(color: LactevaColors.muted),
                  ),
                if (stopItems(stop).isNotEmpty) ...[
                  const SizedBox(height: 20),
                  _SectionLabel(text: t.t('driver.itemsSold')),
                  const SizedBox(height: 10),
                  for (final item in stopItems(stop))
                    _FigureRow(
                      label: '${item['product_name'] ?? item['product']}',
                      figure: '${tidy(double.tryParse('${item['quantity']}') ?? 0)} ${item['unit'] ?? 'pc'}',
                    ),
                ],
              ],
            ),
    );
  }
}

class _ReviewRow extends StatelessWidget {
  const _ReviewRow({required this.order, required this.t, required this.onCorrect});
  final Map<String, dynamic> order;
  final L10n t;
  final Future<void> Function()? onCorrect;

  @override
  Widget build(BuildContext context) {
    final status = order['delivery_status'];
    final unit = '${order['quantity_unit'] ?? 'L'}';
    final recorded = order['quantity_delivered'] ?? order['quantity'];
    final figure = status == 'delivered'
        ? '${tidy(double.tryParse('$recorded') ?? 0)} $unit'
        : t.t('driver.outcome.${status ?? 'scheduled'}');
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(16, 12, 12, 12),
      decoration: BoxDecoration(
        color: LactevaColors.milk,
        border: Border.all(color: LactevaColors.hairline),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${order['product_name'] ?? order['product']}',
                  style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: LactevaColors.ink),
                ),
                Text(
                  '${t.t('driver.pours')}: ${order['quantity']} $unit',
                  style: const TextStyle(fontSize: 12.5, color: LactevaColors.muted),
                ),
                if (order['invoiced'] == true)
                  Text(
                    t.t('driver.onBill'),
                    key: ValueKey('on-bill-${order['product']}'),
                    style: const TextStyle(fontSize: 12.5, color: LactevaColors.muted),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Text(
            figure,
            key: ValueKey('recorded-${order['product']}'),
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: LactevaColors.ink),
          ),
          if (onCorrect != null) ...[
            const SizedBox(width: 8),
            TextButton(
              key: ValueKey('correct-${order['product']}'),
              onPressed: onCorrect,
              child: Text(t.t('driver.correct')),
            ),
          ],
        ],
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Text(
    text.toUpperCase(),
    style: const TextStyle(
      fontSize: 12,
      fontWeight: FontWeight.w700,
      letterSpacing: 0.96,
      color: LactevaColors.muted,
    ),
  );
}

class _Pill extends StatelessWidget {
  const _Pill({required this.text, required this.tint, required this.ink});

  final String text;
  final Color tint;
  final Color ink;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
    decoration: BoxDecoration(
      color: tint,
      borderRadius: BorderRadius.circular(999),
    ),
    child: Text(
      text,
      style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: ink),
    ),
  );
}

class _Empty extends StatelessWidget {
  const _Empty({
    required this.icon,
    required this.title,
    required this.detail,
    required this.client,
    required this.label,
  });

  final IconData icon;
  final String title;
  final String detail;
  final OfflineApiClient client;
  final String label;

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
            const SizedBox(height: 16),
            // The dead end especially needs the way out (D-2): a login with no
            // driver profile is on the wrong account by definition.
            SignOutButton(client: client, label: label),
          ],
        ),
      ),
    );
  }
}
