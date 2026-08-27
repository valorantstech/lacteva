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
    } catch (_) {
      // Transport failure ≠ refusal (P0-PRODUCT-008 D-1).
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Could not reach the platform')));
    }
  }

  /// The stop the driver is standing in front of, or null when the run is done.
  ///
  /// "Open" is the platform's own word for it: `delivery_status` is
  /// `MilkDelivery.status`, and the logistics module deliberately has no
  /// second state machine. Null and `scheduled` both mean nothing has been
  /// recorded yet.
  static Map<String, dynamic>? nextStop(List<Map<String, dynamic>> stops) {
    for (final stop in stops) {
      final outcome = stop['delivery_status'];
      if (outcome == null || outcome == 'scheduled') return stop;
    }
    return null;
  }

  static List<Map<String, dynamic>> openStops(List<Map<String, dynamic>> stops) =>
      stops
          .where((s) =>
              s['delivery_status'] == null || s['delivery_status'] == 'scheduled')
          .toList();

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
      return _Empty(
        icon: Icons.free_breakfast_outlined,
        title: t.t('driver.noRun'),
        detail: t.t('driver.noRunDetail'),
        client: widget.client,
        label: t.t('common.signOut'),
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

/// One run, as the Driver board draws it.
///
/// The board shows a single run because a driver has one; the screen still
/// renders whatever `myRuns()` returned, so a second run gets its own board
/// below the first rather than being hidden.
class _RunBoard extends StatelessWidget {
  const _RunBoard({required this.run, required this.state});

  final Map<String, dynamic> run;
  final _DriverHomeScreenState state;

  @override
  Widget build(BuildContext context) {
    final t = L10n.of(state.widget.session);
    final status = (run['status'] ?? '').toString();
    final stops =
        ((run['stops'] as List?) ?? const []).cast<Map<String, dynamic>>();
    final open = _DriverHomeScreenState.openStops(stops);
    final next = _DriverHomeScreenState.nextStop(stops);
    final runOpen = status == 'in_progress' || status == 'planned';
    final done = stops.length - open.length;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _RunHeader(run: run, done: done, total: stops.length, t: t),
        if (next != null && runOpen)
          _NextStopCard(
            run: run,
            stop: next,
            position: done + 1,
            total: stops.length,
            state: state,
            t: t,
          ),
        if (open.length > 1)
          _ThenList(stops: open.skip(1).toList(), t: t),
        _OnBoardBand(run: run, remaining: open.length, state: state, t: t),
      ],
    );
  }
}

/// Which round this is, and how much of it is left.
class _RunHeader extends StatelessWidget {
  const _RunHeader({
    required this.run,
    required this.done,
    required this.total,
    required this.t,
  });

  final Map<String, dynamic> run;
  final int done;
  final int total;
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
          Row(
            children: [
              Expanded(
                child: Text(
                  t.t('driver.roundTitle', {'slot': t.t('slot.$slot')}),
                  style: const TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.44,
                    color: LactevaColors.ink,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              // The board's chip carried a wall-clock start time. The run's
              // `started_at` is a UTC instant and this app does no timezone
              // arithmetic, so the chip says the STATE instead — which is the
              // thing a driver checks it for. The status arrives as a code and
              // the catalog decides the word, like everything else here.
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
              Text(
                t.t('driver.ofStops', {'done': done, 'total': total}),
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: LactevaColors.ink,
                ),
              ),
            ],
          ),
          const SizedBox(height: 7),
          _ProgressBar(done: done, total: total),
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

/// The one stop that matters, at the size it matters.
///
/// Glanceability is the constraint: a driver reads this through a windscreen
/// with the engine running. The board put a 40px quantity here; a run stop
/// carries no quantity and a DRIVER holds only `logistics.run.execute`, so
/// there is no read that could ever supply one. The big figure is the stop's
/// own position instead — true, and the thing a driver checks against a paper
/// list.
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
                        label: t.t('driver.outcome.delivered'),
                        icon: Icons.check,
                        primary: true,
                        onTap: () =>
                            state._recordOutcome(run, stop, 'delivered'),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      flex: 10,
                      child: _Action(
                        label: t.t('driver.missed'),
                        primary: false,
                        onTap: () => state._recordOutcome(
                          run,
                          stop,
                          'skipped',
                          notes: t.t('driver.skippedDefaultNote'),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// 56dp, because the hands work here.
class _Action extends StatelessWidget {
  const _Action({
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

/// What comes after the one in hand.
class _ThenList extends StatelessWidget {
  const _ThenList({required this.stops, required this.t});

  final List<Map<String, dynamic>> stops;
  final L10n t;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionLabel(text: t.t('driver.then')),
          const SizedBox(height: 10),
          for (var i = 0; i < stops.length; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Opacity(
                // The board dims the far end of the queue: the third stop
                // away is context, not work.
                opacity: i >= 2 ? 0.65 : 1,
                child: _ThenRow(stop: stops[i], dimmed: i >= 2),
              ),
            ),
        ],
      ),
    );
  }
}

class _ThenRow extends StatelessWidget {
  const _ThenRow({required this.stop, required this.dimmed});

  final Map<String, dynamic> stop;
  final bool dimmed;

  @override
  Widget build(BuildContext context) {
    final address = (stop['address'] ?? '').toString();
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
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// The van, and the way off it.
///
/// Dark because it is a FACT rather than a control — the eye passes over it
/// unless it is looking. The board's litres-on-board and loading time have no
/// read behind them (a run carries no quantity, and `logistics.run.execute` is
/// every grant a driver holds), so the band states the run itself. The action
/// is the run transition the platform will actually accept: Start before the
/// run begins, End once every stop is recorded.
class _OnBoardBand extends StatelessWidget {
  const _OnBoardBand({
    required this.run,
    required this.remaining,
    required this.state,
    required this.t,
  });

  final Map<String, dynamic> run;
  final int remaining;
  final _DriverHomeScreenState state;
  final L10n t;

  @override
  Widget build(BuildContext context) {
    final status = (run['status'] ?? '').toString();
    final planned = status == 'planned';
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
                            ? t.t('driver.everyStopRecorded')
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
