/// The manager's own screen (WO-72 Part C · D-23).
///
/// The owner opened the app with a manager's login and got the counter
/// operator's screen: a number with no unit, a chart with no axis, an amber
/// warning that explained nothing, and "Collect milk" as the primary action
/// for someone who will never collect milk. This is the fourth experience
/// the review ruled for — oversight, not operation.
///
/// Three rules, from the review, and each figure below answers to them:
///
///   * **Every figure is comparative or actionable.** A bare `10.5` tells a
///     manager nothing; `412.5 L of ~620 L expected` and `38 of 52 farmers
///     · 14 still to come` tell them whether the morning is going well. The
///     expectation is the SAME WEEKDAY LAST WEEK, read from the platform's
///     own report, not a target anyone typed.
///   * **Every alert states what happened, since when, and what to do.** A
///     severity stripe carries urgency so colour is not doing the work
///     alone; the action is a real control. If there is nothing to do there
///     is no alert.
///   * **Nothing is assumed.** Units come from the record (WO-70); money
///     comes formatted from the platform; the app performs no timezone
///     arithmetic. "As of" is the time THIS PHONE fetched the figure, said
///     as that.
///
/// DS V1.1 governs: the product's own tokens, "extraordinary where the eye
/// rests". Chart text takes its colour from the theme so it survives both.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import 'api.dart';
import 'centers.dart';
import 'format.dart';
import 'l10n.dart';
import 'offline/offline_client.dart';
import 'offline/sync_screen.dart';
import 'session.dart';
import 'suppliers.dart';
import 'theme.dart';
import 'transactions_history.dart';

class ManagerHomeScreen extends StatefulWidget {
  const ManagerHomeScreen({super.key, required this.client, required this.session});

  final ApiClient client;
  final Session session;

  @override
  State<ManagerHomeScreen> createState() => _ManagerHomeScreenState();
}

class _ManagerHomeScreenState extends State<ManagerHomeScreen> {
  CenterSummary? _centre;
  int _centreCount = 0;
  bool _resolving = true;
  String? _error;

  DailySummaryView? _today;
  DailySummaryView? _sameDayLastWeek;
  DailySummaryView? _cycle;
  List<DailySummaryView?> _week = const [];
  int? _activeFarmers;
  ReadinessResultView? _readiness;
  bool _sessionOpen = false;
  DateTime? _fetchedAt;

  L10n get _l => L10n.of(widget.session);

  @override
  void initState() {
    super.initState();
    _resolve();
  }

  Future<void> _resolve() async {
    setState(() {
      _resolving = true;
      _error = null;
    });
    try {
      final page = await widget.client.listCenters(limit: 20, status: 'active');
      final mine = page.items.where((c) => widget.session.coversCenter(c.id)).toList();
      if (!mounted) return;
      setState(() {
        _centre = mine.isEmpty ? null : mine.first;
        _centreCount = mine.length;
        _resolving = false;
      });
      final centre = _centre;
      if (centre != null) await _loadPanels(centre.id);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _resolving = false;
        _error = _l.t('common.couldNotReach');
      });
    }
  }

  /// Independently: one refusal must not blank the others.
  Future<void> _loadPanels(String centreId) async {
    Future<void> panel(Future<void> Function() run) async {
      try {
        await run();
      } catch (_) {}
    }

    await Future.wait([
      panel(() async {
        final today = await widget.client.dailyReport(centreId);
        if (!mounted) return;
        setState(() {
          _today = today;
          _fetchedAt = DateTime.now();
        });
        // Everything comparative hangs off the day the platform said it is.
        final day = today.dateFrom;
        if (day.isEmpty) return;
        await Future.wait([
          panel(() async {
            final lastWeek = await widget.client.dailyReport(centreId, on: shiftDays(day, -7));
            if (mounted) setState(() => _sameDayLastWeek = lastWeek);
          }),
          panel(() async {
            final cycle = await widget.client.dailyReport(
              centreId,
              from: '${day.substring(0, 7)}-01',
              to: day,
            );
            if (mounted) setState(() => _cycle = cycle);
          }),
          panel(() async {
            final days = [for (var i = 6; i >= 1; i--) shiftDays(day, -i)];
            final reports = await Future.wait([
              for (final d in days)
                widget.client.dailyReport(centreId, on: d).then<DailySummaryView?>((r) => r).catchError((_) => null),
            ]);
            if (mounted) setState(() => _week = [...reports, today]);
          }),
        ]);
      }),
      panel(() async {
        final s = await widget.client.listSuppliers(centerId: centreId, limit: 1);
        if (mounted) setState(() => _activeFarmers = s.total);
      }),
      panel(() async {
        final r = await widget.client.readiness(centreId);
        if (mounted) setState(() => _readiness = r);
      }),
      panel(() async {
        final open = await widget.client.listOpenSessions(centreId);
        if (mounted) setState(() => _sessionOpen = open.isNotEmpty);
      }),
    ]);
  }

  void _open(Widget screen) =>
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen)).then((_) {
        final centre = _centre;
        if (centre != null) _loadPanels(centre.id);
      });

  @override
  Widget build(BuildContext context) {
    final l = _l;
    if (_resolving) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final centre = _centre;
    if (_error != null || centre == null) {
      return Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(_error ?? l.t('hub.noCentre'), textAlign: TextAlign.center),
                const SizedBox(height: 16),
                FilledButton(onPressed: _resolve, child: Text(l.t('common.retry'))),
              ],
            ),
          ),
        ),
      );
    }
    final today = _today;
    final unit = today == null ? '' : unitLabel(today.quantityUnit);
    final exceptions = _exceptions(centre);
    return Scaffold(
      backgroundColor: LactevaColors.cream,
      body: RefreshIndicator(
        onRefresh: () => _loadPanels(centre.id),
        child: ListView(
          padding: EdgeInsets.fromLTRB(20, MediaQuery.paddingOf(context).top + 20, 20, 32),
          children: [
            _Header(
              l: l,
              organisation: widget.session.organization?.name ?? '',
              centreName: centre.name,
              canSwitch: _centreCount > 1,
              onSwitch: () => _open(CentersListScreen(client: widget.client, session: widget.session)),
              sessionOpen: _sessionOpen,
            ),
            const SizedBox(height: 16),
            _MorningCard(
              l: l,
              today: today,
              expected: _sameDayLastWeek,
              unit: unit,
              activeFarmers: _activeFarmers,
            ),
            if (today != null && today.byMilkType.isNotEmpty) ...[
              const SizedBox(height: 12),
              _MilkTypes(l: l, shares: today.byMilkType),
            ],
            const SizedBox(height: 12),
            _Money(l: l, today: today, cycle: _cycle),
            if (exceptions.isNotEmpty) ...[
              const SizedBox(height: 20),
              _SectionLabel(text: l.t('mgr.needsYou', {'count': exceptions.length})),
              const SizedBox(height: 8),
              for (final e in exceptions) Padding(padding: const EdgeInsets.only(bottom: 8), child: e),
            ],
            const SizedBox(height: 20),
            _WeekChart(l: l, week: _week, unit: unit),
          ],
        ),
      ),
    );
  }

  /// What needs a person, each with a stripe, a cause, a time and a control.
  List<Widget> _exceptions(CenterSummary centre) {
    final l = _l;
    final asOf = _fetchedAt == null ? '' : l.t('mgr.asOf', {'time': _clock(_fetchedAt!)});
    final rows = <Widget>[];
    final readiness = _readiness;
    if (readiness != null) {
      for (final check in readiness.checks.where((c) => !c.passed)) {
        rows.add(
          _Exception(
            severity: _Severity.critical,
            title: check.rule.replaceAll(RegExp(r'[_.]'), ' '),
            detail: [if (check.detail.isNotEmpty) check.detail, asOf].where((s) => s.isNotEmpty).join(' · '),
            action: l.t('mgr.fix'),
            onAction: () => _open(
              ReadinessScreen(client: widget.client, centerId: centre.id, session: widget.session),
            ),
          ),
        );
      }
    }
    final pending = widget.client is OfflineApiClient ? (widget.client as OfflineApiClient).pendingCount : 0;
    if (pending > 0) {
      rows.add(
        _Exception(
          severity: _Severity.warning,
          title: l.t('mgr.syncTitle', {'count': pending}),
          detail: l.t('mgr.syncDetail'),
          action: l.t('mgr.sync'),
          onAction: () => _open(
            SyncStatusScreen(client: widget.client as OfflineApiClient, session: widget.session),
          ),
        ),
      );
    }
    final today = _today;
    if (today != null && today.unpricedAccepted > 0) {
      rows.add(
        _Exception(
          severity: _Severity.info,
          title: l.t('mgr.unpricedTitle', {'count': today.unpricedAccepted}),
          detail: [l.t('mgr.unpricedDetail'), asOf].join(' · '),
          action: l.t('mgr.review'),
          onAction: () => _open(
            TransactionHistoryScreen(
              client: widget.client,
              centerId: centre.id,
              centerName: centre.name,
              session: widget.session,
            ),
          ),
        ),
      );
    }
    final active = _activeFarmers;
    if (today != null && active != null && active > today.suppliersServed && !today.isEmpty) {
      rows.add(
        _Exception(
          severity: _Severity.warning,
          title: l.t('mgr.farmersTitle', {'count': active - today.suppliersServed}),
          detail: [l.t('mgr.farmersDetail'), asOf].join(' · '),
          action: l.t('mgr.view'),
          onAction: () => _open(SuppliersListScreen(client: widget.client, session: widget.session)),
        ),
      );
    }
    return rows;
  }

  static String _clock(DateTime t) =>
      '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
}

/// `2026-09-04` shifted by whole days — calendar arithmetic on a date the
/// PLATFORM computed, the same rule `DailySummaryView.dayBefore` follows.
String shiftDays(String isoDate, int days) {
  final parts = isoDate.split('-').map(int.tryParse).toList();
  if (parts.length != 3 || parts.any((p) => p == null)) return isoDate;
  final anchor = DateTime.utc(parts[0]!, parts[1]!, parts[2]!, 12).add(Duration(days: days));
  return '${anchor.year.toString().padLeft(4, '0')}-'
      '${anchor.month.toString().padLeft(2, '0')}-'
      '${anchor.day.toString().padLeft(2, '0')}';
}

/// Monday = 0 … Sunday = 6, for a `YYYY-MM-DD` the platform sent.
int weekdayOf(String isoDate) {
  final parts = isoDate.split('-').map(int.tryParse).toList();
  if (parts.length != 3 || parts.any((p) => p == null)) return 0;
  return DateTime.utc(parts[0]!, parts[1]!, parts[2]!).weekday - 1;
}

class _Header extends StatelessWidget {
  const _Header({
    required this.l,
    required this.organisation,
    required this.centreName,
    required this.canSwitch,
    required this.onSwitch,
    required this.sessionOpen,
  });

  final L10n l;
  final String organisation;
  final String centreName;
  final bool canSwitch;
  final VoidCallback onSwitch;
  final bool sessionOpen;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (organisation.isNotEmpty)
                Text(organisation, style: const TextStyle(fontSize: 13, color: LactevaColors.muted)),
              InkWell(
                onTap: canSwitch ? onSwitch : null,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Flexible(
                      child: Text(
                        centreName,
                        style: const TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.w700,
                          letterSpacing: -0.44,
                          color: LactevaColors.ink,
                        ),
                      ),
                    ),
                    if (canSwitch)
                      Semantics(
                        button: true,
                        label: l.t('home.switchCentre'),
                        child: const Icon(Icons.expand_more, size: 18, color: LactevaColors.muted),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: sessionOpen ? LactevaColors.successTint : LactevaColors.neutralTint,
            borderRadius: BorderRadius.circular(999),
          ),
          child: Text(
            sessionOpen ? l.t('mgr.sessionOpen') : l.t('mgr.sessionClosed'),
            style: TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w700,
              color: sessionOpen ? LactevaColors.onSuccessTint : LactevaColors.onNeutralTint,
            ),
          ),
        ),
      ],
    );
  }
}

class _MorningCard extends StatelessWidget {
  const _MorningCard({
    required this.l,
    required this.today,
    required this.expected,
    required this.unit,
    required this.activeFarmers,
  });

  final L10n l;
  final DailySummaryView? today;
  final DailySummaryView? expected;
  final String unit;
  final int? activeFarmers;

  @override
  Widget build(BuildContext context) {
    final t = today;
    final e = expected;
    final collected = t?.totalNetWeightKg;
    final target = e == null || e.totalNetWeightKg <= 0 ? null : e.totalNetWeightKg;
    final fraction = collected == null || target == null ? null : (collected / target).clamp(0.0, 1.0);
    String? delta;
    if (collected != null && target != null && t != null) {
      final pct = ((collected - target) / target * 100);
      final day = l.t('day.name.${weekdayOf(t.dateFrom)}');
      delta = pct.abs() < 0.05
          ? l.t('mgr.level', {'day': day})
          : l.t(pct > 0 ? 'mgr.up' : 'mgr.down', {'pct': pct.abs().toStringAsFixed(1), 'day': day});
    }
    final served = t?.suppliersServed;
    final active = activeFarmers;
    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _Label(l.t('mgr.morningCollection')),
              if (delta != null)
                Text(
                  delta,
                  key: const ValueKey('mgr-delta'),
                  style: TextStyle(
                    fontSize: 11.5,
                    fontWeight: FontWeight.w600,
                    color: delta.startsWith('▼') ? LactevaColors.warning : LactevaColors.success,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                quantityValue(collected),
                key: const ValueKey('mgr-hero'),
                style: const TextStyle(
                  fontSize: 38,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -1.3,
                  height: 1,
                  color: LactevaColors.ink,
                ),
              ),
              if (unit.isNotEmpty && collected != null)
                Padding(
                  padding: const EdgeInsets.only(left: 6, bottom: 3),
                  child: Text(
                    unit,
                    key: const ValueKey('mgr-unit'),
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: LactevaColors.muted),
                  ),
                ),
              const Spacer(),
              Text(
                target == null
                    ? l.t('mgr.noExpectation')
                    : l.t('mgr.expected', {'value': quantityValue(target), 'unit': unit}),
                key: const ValueKey('mgr-expected'),
                style: const TextStyle(fontSize: 11, color: LactevaColors.faint),
                textAlign: TextAlign.end,
              ),
            ],
          ),
          if (fraction != null) ...[
            const SizedBox(height: 11),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                key: const ValueKey('mgr-progress'),
                value: fraction,
                minHeight: 7,
                backgroundColor: LactevaColors.milkFill,
                color: LactevaColors.dairy,
              ),
            ),
          ],
          if (served != null) ...[
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  active == null
                      ? l.t('manager.farmersServed', {'count': served})
                      : l.t('mgr.farmersOf', {'served': served, 'total': active}),
                  style: const TextStyle(fontSize: 11.5, color: LactevaColors.muted),
                ),
                if (active != null)
                  Text(
                    l.t('mgr.stillToCome', {'count': (active - served).clamp(0, active)}),
                    style: const TextStyle(fontSize: 11.5, color: LactevaColors.muted),
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _MilkTypes extends StatelessWidget {
  const _MilkTypes({required this.l, required this.shares});

  final L10n l;
  final List<MilkTypeShare> shares;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (var i = 0; i < shares.length; i++) ...[
          if (i > 0) const SizedBox(width: 8),
          Expanded(
            child: _Card(
              padding: const EdgeInsets.fromLTRB(12, 9, 12, 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    l.t('milk.${shares[i].milkType}'),
                    style: const TextStyle(fontSize: 10.5, fontWeight: FontWeight.w600, color: LactevaColors.faint),
                  ),
                  const SizedBox(height: 2),
                  // WO-70: the unit the REPORT carried for this row.
                  Text(
                    quantity(shares[i].netWeightKg, unit: unitLabel(shares[i].quantityUnit)),
                    style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600, color: LactevaColors.ink),
                  ),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _Money extends StatelessWidget {
  const _Money({required this.l, required this.today, required this.cycle});

  final L10n l;
  final DailySummaryView? today;
  final DailySummaryView? cycle;

  @override
  Widget build(BuildContext context) {
    Widget cell(String label, String value, Key key) => Expanded(
      child: _Card(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _Label(label),
            const SizedBox(height: 4),
            Text(
              value,
              key: key,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: LactevaColors.ink),
            ),
          ],
        ),
      ),
    );
    // The platform formats the payable WITH its currency (`payable_by_currency`);
    // an empty one means nothing priced yet, and says so with a dash.
    String money(DailySummaryView? r) => r == null || r.payable.isEmpty ? '—' : r.payable;
    return Row(
      children: [
        cell(l.t('mgr.payableToday'), money(today), const ValueKey('mgr-payable-today')),
        const SizedBox(width: 8),
        cell(l.t('mgr.thisCycle'), money(cycle), const ValueKey('mgr-payable-cycle')),
      ],
    );
  }
}

enum _Severity { critical, warning, info }

class _Exception extends StatelessWidget {
  const _Exception({
    required this.severity,
    required this.title,
    required this.detail,
    required this.action,
    required this.onAction,
  });

  final _Severity severity;
  final String title;
  final String detail;
  final String action;
  final VoidCallback onAction;

  @override
  Widget build(BuildContext context) {
    final stripe = switch (severity) {
      _Severity.critical => LactevaColors.danger,
      _Severity.warning => LactevaColors.warning,
      _Severity.info => LactevaColors.water,
    };
    return _Card(
      padding: const EdgeInsets.fromLTRB(12, 11, 12, 11),
      child: Row(
        children: [
          Container(
            width: 3,
            height: 34,
            decoration: BoxDecoration(color: stripe, borderRadius: BorderRadius.circular(3)),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600, color: LactevaColors.ink)),
                if (detail.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(detail, style: const TextStyle(fontSize: 11, color: LactevaColors.faint)),
                  ),
              ],
            ),
          ),
          TextButton(
            onPressed: onAction,
            child: Text(
              action,
              style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.3, color: LactevaColors.dairy),
            ),
          ),
        ],
      ),
    );
  }
}

/// Seven mornings, with a value axis, a named average and today emphasised.
class _WeekChart extends StatelessWidget {
  const _WeekChart({required this.l, required this.week, required this.unit});

  final L10n l;
  final List<DailySummaryView?> week;
  final String unit;

  @override
  Widget build(BuildContext context) {
    final axisColor = Theme.of(context).colorScheme.onSurfaceVariant;
    final points = week.where((r) => r != null).cast<DailySummaryView>().toList();
    if (points.length < 2) {
      return _Card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _Label(l.t('mgr.last7')),
            const SizedBox(height: 6),
            Text(l.t('mgr.noHistory'), style: TextStyle(fontSize: 12, color: axisColor)),
          ],
        ),
      );
    }
    final values = points.map((r) => r.totalNetWeightKg).toList();
    final max = values.reduce((a, b) => a > b ? a : b);
    final avg = values.reduce((a, b) => a + b) / values.length;
    final scale = max <= 0 ? 1.0 : max;
    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _Label(l.t('mgr.last7')),
              Text(unit, style: TextStyle(fontSize: 10, color: axisColor)),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(quantityValue(max), key: const ValueKey('chart-max'), style: TextStyle(fontSize: 9.5, color: axisColor)),
              Text(
                l.t('mgr.avg', {'value': quantityValue(avg)}),
                key: const ValueKey('chart-avg'),
                style: TextStyle(fontSize: 9.5, color: axisColor),
              ),
            ],
          ),
          const SizedBox(height: 4),
          SizedBox(
            height: 64,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                for (var i = 0; i < points.length; i++) ...[
                  if (i > 0) const SizedBox(width: 6),
                  Expanded(
                    child: Semantics(
                      label: '${l.t('day.name.${weekdayOf(points[i].dateFrom)}')} '
                          '${quantity(points[i].totalNetWeightKg, unit: unit)}',
                      child: FractionallySizedBox(
                        heightFactor: (points[i].totalNetWeightKg / scale).clamp(0.02, 1.0),
                        alignment: Alignment.bottomCenter,
                        child: Container(
                          decoration: BoxDecoration(
                            // Today is the emphasised endpoint; the rest read as context.
                            color: i == points.length - 1 ? LactevaColors.dairy : LactevaColors.milkFill,
                            borderRadius: const BorderRadius.vertical(top: Radius.circular(3)),
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
          Container(height: 1, color: LactevaColors.hairline),
          const SizedBox(height: 4),
          Row(
            children: [
              for (var i = 0; i < points.length; i++) ...[
                if (i > 0) const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    l.t('day.short.${weekdayOf(points[i].dateFrom)}'),
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 9, color: axisColor),
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.child, this.padding = const EdgeInsets.all(14)});

  final Widget child;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: LactevaColors.milk,
        border: Border.all(color: LactevaColors.hairline),
        borderRadius: BorderRadius.circular(15),
      ),
      child: child,
    );
  }
}

class _Label extends StatelessWidget {
  const _Label(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Text(
    text.toUpperCase(),
    style: const TextStyle(fontSize: 9.5, letterSpacing: 1.2, fontWeight: FontWeight.w600, color: LactevaColors.faint),
  );
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Text(
    text.toUpperCase(),
    style: const TextStyle(fontSize: 11, letterSpacing: 1.1, fontWeight: FontWeight.w700, color: LactevaColors.muted),
  );
}
