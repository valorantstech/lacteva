/// Where the collection day starts (LACTEVA-MOBILE-005; boards: Main,
/// CentreManager).
///
/// Until now a sign-in landed on a paginated list of collection centres, and
/// the centre's work hung off an icon strip in the app bar: six unlabelled
/// glyphs, two of which a COLLECTION_OPERATOR could not open at all until
/// LACTEVA-MOBILE-002 hid them. A list is a correct answer to "which centre",
/// and an answer to nothing else an operator has at 5 a.m.
///
/// So this is a HOME: the centre, whether the shift is open, what has been
/// collected so far, and one obvious way to start the next collection. The
/// inner screens are unchanged and reached from here — this work order adds a
/// home and the routing to it, and rewrites nothing behind it. The icon strip
/// stays where it is on those screens.
///
/// **The governing rule, and what it forbids here.** *Extraordinary where the
/// eye rests, invisible where the hands work.* The eye rests on this screen;
/// the hands work in the wizard. So the hero may be a gradient and the
/// numbers may be large — but NOTHING on this screen may stand between a tap
/// and the capture path. There is no animation here at all, and the Collect
/// card is built and armed on the first frame, before any read has answered.
/// A queue of farmers does not wait for a summary.
///
/// **Two variants, chosen by capability.** A principal who can read reporting
/// gets the manager board — the readiness chip, the morning card, the
/// needs-a-look list — because that is precisely the grant those panels are
/// made of, and offering a panel the platform will refuse is the defect
/// LACTEVA-MOBILE-002 was raised for. Never a role name: DEMO-008 made roles
/// editable rows, and a client that switched on `CENTRE_MANAGER` would be
/// wrong the moment a dairy created a role doing the same job under another
/// name.
library;

import 'package:flutter/material.dart';

import 'api.dart';
import 'center_summary.dart';
import 'centers.dart';
import 'collection_wizard.dart';
import 'l10n.dart';
import 'offline/offline_client.dart';
import 'offline/sync_screen.dart';
import 'session.dart';
import 'sign_out.dart';
import 'suppliers.dart';
import 'theme.dart';
import 'transactions_history.dart';

/// Which greeting the hero opens with.
///
/// The HANDSET's hour, deliberately, and the one place in this app that reads
/// it. Everywhere else the rule holds absolutely: a business date or a
/// business time comes from the platform, already computed in the dairy's
/// clock, and is rendered verbatim — a phone left on the wrong setting must
/// never move a business day. A greeting is not a business fact. It greets
/// the person holding the phone, and their morning is the phone's morning.
String greetingKeyForHour(int hour) {
  if (hour < 12) return 'home.greetingMorning';
  if (hour < 17) return 'home.greetingAfternoon';
  return 'home.greetingEvening';
}

/// The collection experience's landing screen.
///
/// Resolves which centre this is a home FOR, then renders the variant the
/// session's capabilities earn.
class CollectionHomeScreen extends StatefulWidget {
  const CollectionHomeScreen({
    super.key,
    required this.client,
    required this.session,
    this.hourOfDay,
  });

  final OfflineApiClient client;
  final Session session;

  /// Injected by the tests so the greeting is deterministic; null reads the
  /// handset clock.
  final int? hourOfDay;

  @override
  State<CollectionHomeScreen> createState() => _CollectionHomeScreenState();
}

class _CollectionHomeScreenState extends State<CollectionHomeScreen> {
  L10n get _l => L10n.of(widget.session);

  CenterSummary? _centre;
  int _centreCount = 0;
  CenterDetail? _detail;
  DailySummaryView? _summary;
  ReadinessResultView? _readiness;
  List<Map<String, dynamic>> _openSessions = const [];
  List<Map<String, dynamic>> _recent = const [];
  RateCardSummary? _rateCard;

  bool _resolving = true;
  String? _error;

  bool get _isManagerView => widget.session.can('reporting.read');

  @override
  void initState() {
    super.initState();
    _resolve();
  }

  /// Which centre, then everything about it.
  ///
  /// Split in two on purpose: the centre is the only thing the rest depends
  /// on, and every panel below it is allowed to fail on its own. A summary
  /// the platform refuses must cost its own card and not the screen — the
  /// same discipline `/centers/[id]` uses in the portal.
  Future<void> _resolve() async {
    setState(() {
      _resolving = true;
      _error = null;
    });
    try {
      final page = await widget.client.listCenters(limit: 20, status: 'active');
      // A centre-scoped operator must not be offered another centre's work.
      // The platform enforces this too; this is so the app never shows a door
      // that slams.
      final mine = page.items
          .where((c) => widget.session.coversCenter(c.id))
          .toList();
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

  Future<void> _loadPanels(String centreId) async {
    // Independently: one refusal must not blank the others.
    Future<void> panel(Future<void> Function() run) async {
      try {
        await run();
      } catch (_) {
        // The card renders its absence; the screen stays up.
      }
    }

    await Future.wait([
      panel(() async {
        final d = await widget.client.centerDetail(centreId);
        if (mounted) setState(() => _detail = d);
      }),
      panel(() async {
        final s = await widget.client.dailyReport(centreId);
        if (mounted) setState(() => _summary = s);
      }),
      panel(() async {
        final o = await widget.client.listOpenSessions(centreId);
        if (mounted) setState(() => _openSessions = o);
      }),
      panel(() async {
        final r = await widget.client.listMilkTransactions(
          centerId: centreId,
          limit: 6,
        );
        final items = (r['items'] as List<dynamic>? ?? const [])
            .map((e) => (e as Map).cast<String, dynamic>())
            .toList();
        if (mounted) setState(() => _recent = items);
      }),
      if (_isManagerView)
        panel(() async {
          final r = await widget.client.readiness(centreId);
          if (mounted) setState(() => _readiness = r);
        }),
      // The footer fact, and the one panel gated on its OWN grant rather than
      // on the variant: a manager may read reporting without reading pricing.
      if (widget.session.can('pricing.ratecard.read'))
        panel(() async {
          final cards = await widget.client.listRateCards(
            status: 'published',
            limit: 1,
          );
          if (mounted && cards.items.isNotEmpty) {
            setState(() => _rateCard = cards.items.first);
          }
        }),
    ]);
  }

  // -------------------------------------------------------------------
  // Navigation. Every destination is an EXISTING screen.
  // -------------------------------------------------------------------

  void _open(Widget screen) {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));
  }

  /// The one action this screen exists to make fast.
  ///
  /// Identical to what the centre toolbar has always done — reuse the open
  /// session, open one if there is none, then the wizard. It runs on tap
  /// rather than on load so that arriving here costs nothing, and it is armed
  /// from the first frame: `_centre` is the only thing it needs, and if the
  /// centre has not resolved yet the card is disabled rather than absent, so
  /// the layout never moves under a thumb already travelling towards it.
  Future<void> _collect() async {
    final centre = _centre;
    if (centre == null) return;
    final t = _l;
    try {
      final open = await widget.client.listOpenSessions(centre.id);
      final session = open.isNotEmpty
          ? open.first
          : await widget.client.openCollectionSession(centre.id);
      if (!mounted) return;
      await Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => CollectionWizardScreen(
            client: widget.client,
            sessionId: session['id'] as String,
            session: widget.session,
          ),
        ),
      );
      if (mounted) await _loadPanels(centre.id);
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

  @override
  Widget build(BuildContext context) {
    final t = _l;
    if (_resolving) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final centre = _centre;
    if (centre == null) {
      return Scaffold(
        appBar: AppBar(
          title: const Text('Lacteva'),
          actions: [SignOutButton(client: widget.client)],
        ),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  _error ?? t.t('home.noCentre'),
                  style: Theme.of(context).textTheme.titleMedium,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                Text(
                  t.t('home.noCentreDetail'),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: _resolve,
                  child: Text(t.t('common.retry')),
                ),
              ],
            ),
          ),
        ),
      );
    }

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _resolve,
        child: ListView(
          padding: EdgeInsets.zero,
          children: _isManagerView
              ? _managerBoard(centre)
              : _operatorBoard(centre),
        ),
      ),
    );
  }

  // ===================================================================
  // The operator board (Main.dc.html)
  // ===================================================================

  List<Widget> _operatorBoard(CenterSummary centre) => [
    _HeroBand(
      greeting: _l.t(greetingKeyForHour(widget.hourOfDay ?? DateTime.now().hour), {
        'name': _firstName(widget.session.fullName),
      }),
      centreName: centre.name,
      sessionOpen: _openSessions.isNotEmpty,
      sessionLabel: _openSessions.isNotEmpty
          ? _l.t('home.sessionOpen')
          : _l.t('home.sessionClosed'),
      metrics: [
        (_litres(_summary?.totalNetWeightKg), _l.t('home.collectedToday')),
        ('${_summary?.suppliersServed ?? "—"}', _l.t('home.farmers')),
        ('${_summary?.avgFat ?? "—"}', _l.t('home.avgFat')),
      ],
      onSignOut: SignOutButton(client: widget.client),
    ),
    Padding(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 0),
      child: _CollectCard(label: _l.t('home.collectMilk'), detail: _l.t('home.collectMilkDetail'), onTap: _collect),
    ),
    Padding(
      padding: const EdgeInsets.all(20),
      child: _NavGrid(tiles: _operatorTiles(centre)),
    ),
    _LastCollection(l: _l, tx: _recent.isEmpty ? null : _recent.first),
    _FooterFact(text: _shiftFooter(centre)),
  ];

  List<_NavTile> _operatorTiles(CenterSummary centre) {
    final pending = widget.client.pendingCount;
    return [
      _NavTile(
        icon: Icons.receipt_long_outlined,
        label: _l.t('home.todaysCollections'),
        onTap: () => _open(
          TransactionHistoryScreen(
            client: widget.client,
            centerId: centre.id,
            centerName: centre.name,
            session: widget.session,
          ),
        ),
      ),
      _NavTile(
        icon: Icons.groups_outlined,
        label: _l.t('home.farmersTile'),
        onTap: () => _open(
          SuppliersListScreen(client: widget.client, session: widget.session),
        ),
      ),
      _NavTile(
        icon: Icons.sync,
        iconColor: LactevaColors.water,
        label: _l.t('home.sync'),
        // The chip is the queue's own count, not a guess: `pendingCount` is
        // what the offline store holds this instant.
        chip: pending == 0
            ? _l.t('home.syncAllSent')
            : _l.t('home.syncWaiting', {'count': pending}),
        chipIsQuiet: pending == 0,
        onTap: () => _open(
          SyncStatusScreen(client: widget.client, session: widget.session),
        ),
      ),
      _NavTile(
        icon: Icons.schedule_outlined,
        label: _l.t('home.shiftHistory'),
        onTap: () => _open(
          CenterDetailScreen(
            client: widget.client,
            centerId: centre.id,
            session: widget.session,
          ),
        ),
      ),
    ];
  }

  // ===================================================================
  // The manager board (CentreManager.dc.html)
  // ===================================================================

  List<Widget> _managerBoard(CenterSummary centre) => [
    _ManagerHeader(
      l: _l,
      // NOT a role name — the house rule forbids branching on one and this
      // would be printing one. The board's small line above the centre is the
      // context a manager actually lacks: which dairy this centre belongs to.
      context: widget.session.organization?.name ?? '',
      centreName: centre.name,
      canSwitch: _centreCount > 1,
      onSwitch: () => _open(
        CentersListScreen(client: widget.client, session: widget.session),
      ),
      readiness: _readiness,
      signOut: SignOutButton(client: widget.client),
    ),
    Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 0),
      child: _MorningCard(
        l: _l,
        litres: _litres(_summary?.totalNetWeightKg),
        window: _todayWindow(),
        farmers: _summary?.suppliersServed,
        // The board's six bars carry no axis and no hour labels, and the
        // platform exposes no hourly bucket for a centre — so these are the
        // last six collections by quantity, newest last and highlighted.
        // Real numbers from a read that already exists, and no clock
        // arithmetic, which the app does not do.
        bars: _recent.reversed
            .map((tx) => double.tryParse('${tx['net_weight'] ?? 0}') ?? 0)
            .toList(),
      ),
    ),
    Padding(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 0),
      child: _NavGrid(tiles: _managerTiles(centre)),
    ),
    _NeedsALook(l: _l, readiness: _readiness, unpriced: _summary?.unpricedAccepted ?? 0),
    _FooterFact(text: _rateCardFooter() ?? _shiftFooter(centre)),
  ];

  List<_NavTile> _managerTiles(CenterSummary centre) => [
    _NavTile(
      icon: Icons.water_drop_outlined,
      label: _l.t('home.collectMilk'),
      onTap: _collect,
    ),
    _NavTile(
      icon: Icons.bar_chart_outlined,
      label: _l.t('manager.todaysSummary'),
      onTap: () => _open(
        CenterTodayScreen(
          client: widget.client,
          centerId: centre.id,
          session: widget.session,
        ),
      ),
    ),
    _NavTile(
      icon: Icons.calendar_month_outlined,
      label: _l.t('manager.centreCalendar'),
      onTap: () => _open(
        CenterDetailScreen(
          client: widget.client,
          centerId: centre.id,
          session: widget.session,
        ),
      ),
    ),
  ];

  // -------------------------------------------------------------------
  // Values the boards show, from reads that already exist.
  // -------------------------------------------------------------------

  static String _firstName(String full) =>
      full.trim().isEmpty ? '' : full.trim().split(RegExp(r'\s+')).first;

  /// The platform sends kilograms; the board reads litres because that is the
  /// word at the counter. The NUMBER is not converted — it is the platform's
  /// own figure, and inventing a density here would be arithmetic on a
  /// business fact.
  static String _litres(double? kg) => kg == null ? '—' : '$kg';

  /// Today's operating window, in the DAIRY's clock — the platform sends
  /// `opens`/`closes` as plain local times, already resolved. The open
  /// session's `opened_at` is a UTC instant and is deliberately not used:
  /// rendering it as a wall clock would be off by the dairy's offset.
  String? _todayWindow() {
    final windows = _detail?.windows ?? const <OperatingWindowView>[];
    if (windows.isEmpty) return null;
    return windows.first.label;
  }

  String _shiftFooter(CenterSummary centre) {
    final window = _todayWindow();
    return window == null
        ? _l.t('home.centreFooter', {'centre': centre.name, 'code': centre.code})
        : _l.t('home.shiftFooter', {
            'window': window,
            'centre': centre.name,
            'code': centre.code,
          });
  }

  String? _rateCardFooter() {
    final card = _rateCard;
    if (card == null) return null;
    return _l.t('manager.rateCardFooter', {
      'version': card.version,
      'date': businessDate(card.effectiveFrom),
    });
  }
}

// =====================================================================
// The pieces, in board order.
// =====================================================================

/// The hero band: the greeting, the centre, whether the shift is open, and
/// the three figures that answer "how is it going".
class _HeroBand extends StatelessWidget {
  const _HeroBand({
    required this.greeting,
    required this.centreName,
    required this.sessionOpen,
    required this.sessionLabel,
    required this.metrics,
    required this.onSignOut,
  });

  final String greeting;
  final String centreName;
  final bool sessionOpen;
  final String sessionLabel;
  final List<(String, String)> metrics;
  final Widget onSignOut;

  @override
  Widget build(BuildContext context) {
    final top = MediaQuery.paddingOf(context).top;
    return Container(
      // The board's 64px top padding is a status bar plus breathing room; the
      // real inset is whatever this handset has.
      padding: EdgeInsets.fromLTRB(20, top + 20, 20, 22),
      decoration: BoxDecoration(gradient: brandGradient()),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      greeting,
                      style: const TextStyle(
                        color: LactevaColors.onBrandMuted,
                        fontSize: 13,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      centreName,
                      style: const TextStyle(
                        color: LactevaColors.onBrand,
                        fontSize: 22,
                        fontWeight: FontWeight.w700,
                        // The board's -0.02em, resolved against 22px.
                        letterSpacing: -0.44,
                      ),
                    ),
                  ],
                ),
              ),
              _SessionPill(open: sessionOpen, label: sessionLabel),
              onSignOut,
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              for (final (value, label) in metrics) ...[
                Expanded(child: _HeroMetric(value: value, label: label)),
                if (label != metrics.last.$2) const SizedBox(width: 10),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

class _SessionPill extends StatelessWidget {
  const _SessionPill({required this.open, required this.label});

  final bool open;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: LactevaColors.onBrand.withValues(alpha: 0.14),
        border: Border.all(
          color: LactevaColors.onBrand.withValues(alpha: 0.25),
        ),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Never colour alone: the dot is the fast signal, the word is the
          // accessible one, and both are always rendered.
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: open
                  ? LactevaColors.onBrandLive
                  : LactevaColors.onBrandFaint,
            ),
          ),
          const SizedBox(width: 7),
          Text(
            label,
            style: const TextStyle(
              color: LactevaColors.onBrand,
              fontSize: 12.5,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

class _HeroMetric extends StatelessWidget {
  const _HeroMetric({required this.value, required this.label});

  final String value;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: LactevaColors.onBrand.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(12),
      ),
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
                color: LactevaColors.onBrand,
                fontSize: 21,
                fontWeight: FontWeight.w700,
                letterSpacing: -0.21,
              ),
            ),
          ),
          const SizedBox(height: 1),
          Text(
            label,
            style: const TextStyle(
              color: LactevaColors.onBrandFaint,
              fontSize: 11.5,
            ),
          ),
        ],
      ),
    );
  }
}

/// THE primary action, and the reason this screen exists.
///
/// Lifted off the page with the board's two-layer shadow — a close, neutral
/// contact shadow and a wide, green-tinted one — so that the eye finds it
/// before it finds anything else on the screen.
class _CollectCard extends StatelessWidget {
  const _CollectCard({
    required this.label,
    required this.detail,
    required this.onTap,
  });

  final String label;
  final String detail;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: LactevaColors.milk,
      borderRadius: BorderRadius.circular(18),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(18),
        child: Ink(
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
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Row(
              children: [
                Container(
                  width: 62,
                  height: 62,
                  decoration: BoxDecoration(
                    gradient: brandGradient(),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: const Icon(
                    Icons.water_drop,
                    size: 30,
                    color: LactevaColors.onBrand,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        label,
                        style: const TextStyle(
                          fontSize: 19,
                          fontWeight: FontWeight.w700,
                          letterSpacing: -0.19,
                          color: LactevaColors.ink,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        detail,
                        style: const TextStyle(
                          fontSize: 13,
                          color: LactevaColors.muted,
                        ),
                      ),
                    ],
                  ),
                ),
                const Icon(
                  Icons.chevron_right,
                  size: 22,
                  color: LactevaColors.dairy,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The named grid that replaced the icon strip.
///
/// Named, because six unlabelled glyphs in an app bar is a memory test. The
/// tiles wrap rather than assuming two columns, so a large text scale grows
/// the grid instead of clipping the words.
class _NavGrid extends StatelessWidget {
  const _NavGrid({required this.tiles});

  final List<_NavTile> tiles;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        const gap = 12.0;
        final width = (constraints.maxWidth - gap) / 2;
        return Wrap(
          spacing: gap,
          runSpacing: gap,
          children: [
            for (final tile in tiles) SizedBox(width: width, child: tile),
          ],
        );
      },
    );
  }
}

class _NavTile extends StatelessWidget {
  const _NavTile({
    required this.icon,
    required this.label,
    required this.onTap,
    this.chip,
    this.chipIsQuiet = true,
    this.iconColor = LactevaColors.dairy,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final String? chip;
  final bool chipIsQuiet;
  final Color iconColor;

  @override
  Widget build(BuildContext context) {
    final chipText = chip;
    return Material(
      color: LactevaColors.milk,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Ink(
          decoration: BoxDecoration(
            color: LactevaColors.milk,
            border: Border.all(color: LactevaColors.hairline),
            borderRadius: BorderRadius.circular(14),
          ),
          child: ConstrainedBox(
            // Every tappable thing clears 48dp; a named door clears it twice.
            constraints: const BoxConstraints(
              minHeight: LactevaMetrics.minTouchTarget * 1.5,
            ),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Icon(icon, size: 22, color: iconColor),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 7,
                    runSpacing: 4,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      Text(
                        label,
                        style: const TextStyle(
                          fontSize: 14.5,
                          fontWeight: FontWeight.w600,
                          color: LactevaColors.ink,
                        ),
                      ),
                      if (chipText != null)
                        _Chip(text: chipText, quiet: chipIsQuiet),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.text, required this.quiet});

  final String text;
  final bool quiet;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: quiet ? LactevaColors.successTint : LactevaColors.warningTint,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: quiet
              ? LactevaColors.onSuccessTint
              : LactevaColors.warning,
        ),
      ),
    );
  }
}

/// The last thing that happened, because that is what a farmer asks about.
class _LastCollection extends StatelessWidget {
  const _LastCollection({required this.l, required this.tx});

  final L10n l;
  final Map<String, dynamic>? tx;

  @override
  Widget build(BuildContext context) {
    final row = tx;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionLabel(text: l.t('home.lastCollection')),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            decoration: BoxDecoration(
              color: LactevaColors.milk,
              border: Border.all(color: LactevaColors.hairline),
              borderRadius: BorderRadius.circular(14),
            ),
            child: row == null
                ? Text(
                    l.t('home.noCollectionsYet'),
                    style: const TextStyle(
                      fontSize: 13.5,
                      color: LactevaColors.muted,
                    ),
                  )
                : Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '${row['slip_number'] ?? row['id'] ?? ''}',
                              style: const TextStyle(
                                fontSize: 14.5,
                                fontWeight: FontWeight.w600,
                                color: LactevaColors.ink,
                              ),
                            ),
                            const SizedBox(height: 1),
                            Text(
                              [
                                if (row['net_weight'] != null)
                                  '${row['net_weight']} kg',
                                if (row['fat_percentage'] != null)
                                  'FAT ${row['fat_percentage']}',
                                if (row['gross_amount'] != null)
                                  '${row['gross_amount']}',
                              ].join(' · '),
                              style: const TextStyle(
                                fontSize: 12.5,
                                color: LactevaColors.muted,
                              ),
                            ),
                          ],
                        ),
                      ),
                      Text(
                        '${row['state'] ?? ''}',
                        style: const TextStyle(
                          fontSize: 12,
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

class _FooterFact extends StatelessWidget {
  const _FooterFact({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(20, 26, 20, 26),
    child: Center(
      child: Text(
        text,
        textAlign: TextAlign.center,
        style: const TextStyle(fontSize: 11.5, color: LactevaColors.faint),
      ),
    ),
  );
}

// ---------------------------------------------------------------------
// Manager pieces.
// ---------------------------------------------------------------------

class _ManagerHeader extends StatelessWidget {
  const _ManagerHeader({
    required this.l,
    required this.context,
    required this.centreName,
    required this.canSwitch,
    required this.onSwitch,
    required this.readiness,
    required this.signOut,
  });

  final L10n l;
  final String context;
  final String centreName;
  final bool canSwitch;
  final VoidCallback onSwitch;
  final ReadinessResultView? readiness;
  final Widget signOut;

  @override
  Widget build(BuildContext ctx) {
    final top = MediaQuery.paddingOf(ctx).top;
    final r = readiness;
    final passed = r?.checks.where((c) => c.passed).length;
    return Padding(
      padding: EdgeInsets.fromLTRB(20, top + 20, 20, 16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (context.isNotEmpty)
                  Text(
                    context,
                    style: const TextStyle(
                      fontSize: 13,
                      color: LactevaColors.muted,
                    ),
                  ),
                const SizedBox(height: 2),
                // The chevron is only drawn when it does something: a manager
                // of one centre has nothing to switch to.
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
                          child: const Icon(
                            Icons.expand_more,
                            size: 18,
                            color: LactevaColors.muted,
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          if (r != null)
            _ReadinessChip(
              ready: r.status == 'ready',
              text: r.status == 'ready'
                  ? l.t('manager.ready', {
                      'passed': passed,
                      'total': r.checks.length,
                    })
                  : l.t('manager.notReady'),
            ),
          signOut,
        ],
      ),
    );
  }
}

class _ReadinessChip extends StatelessWidget {
  const _ReadinessChip({required this.ready, required this.text});

  final bool ready;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: ready ? LactevaColors.successTint : LactevaColors.warningTint,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            ready ? Icons.check : Icons.priority_high,
            size: 15,
            color: ready ? LactevaColors.success : LactevaColors.warning,
          ),
          const SizedBox(width: 7),
          Text(
            text,
            style: TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w700,
              color: ready
                  ? LactevaColors.onSuccessTint
                  : LactevaColors.warning,
            ),
          ),
        ],
      ),
    );
  }
}

/// The morning at a glance: the figure, the shape, and who it came from.
class _MorningCard extends StatelessWidget {
  const _MorningCard({
    required this.l,
    required this.litres,
    required this.window,
    required this.farmers,
    required this.bars,
  });

  final L10n l;
  final String litres;
  final String? window;
  final int? farmers;
  final List<double> bars;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
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
            color: LactevaColors.dairy.withValues(alpha: 0.08),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              _SectionLabel(text: l.t('manager.thisMorning')),
              if (window != null)
                Flexible(
                  child: Text(
                    window!,
                    textAlign: TextAlign.end,
                    style: const TextStyle(
                      fontSize: 12,
                      color: LactevaColors.muted,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                litres,
                style: const TextStyle(
                  fontSize: 34,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.68,
                  color: LactevaColors.ink,
                ),
              ),
              const SizedBox(width: 16),
              if (bars.isNotEmpty)
                Expanded(child: _RecentBars(bars: bars, l: l)),
            ],
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.only(top: 12),
            decoration: const BoxDecoration(
              border: Border(
                top: BorderSide(color: LactevaColors.divider),
              ),
            ),
            child: Text(
              farmers == null
                  ? l.t('manager.noFigures')
                  : l.t('manager.farmersServed', {'count': farmers}),
              style: const TextStyle(
                fontSize: 12.5,
                color: LactevaColors.muted,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// The board's six quiet columns.
///
/// Not a time series: the platform exposes no hourly bucket for a centre, and
/// the board's bars carry no axis. These are the last six collections by
/// quantity, oldest first, with the newest lit — the SHAPE of the morning
/// from a read that already exists, and no clock arithmetic, which this app
/// does not do.
class _RecentBars extends StatelessWidget {
  const _RecentBars({required this.bars, required this.l});

  final List<double> bars;
  final L10n l;

  @override
  Widget build(BuildContext context) {
    final peak = bars.fold<double>(0, (a, b) => b > a ? b : a);
    return Semantics(
      label: l.t('manager.recentShape', {'count': bars.length}),
      child: SizedBox(
        height: 52,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            for (var i = 0; i < bars.length; i++) ...[
              Expanded(
                child: FractionallySizedBox(
                  heightFactor: peak <= 0
                      ? 0.08
                      : (bars[i] / peak).clamp(0.08, 1.0),
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: i == bars.length - 1
                          ? const LinearGradient(
                              begin: Alignment.topCenter,
                              end: Alignment.bottomCenter,
                              colors: [
                                LactevaColors.fresh,
                                LactevaColors.success,
                              ],
                            )
                          : null,
                      color: i == bars.length - 1
                          ? null
                          : LactevaColors.quietBar,
                      borderRadius: const BorderRadius.vertical(
                        top: Radius.circular(4),
                      ),
                    ),
                  ),
                ),
              ),
              if (i != bars.length - 1) const SizedBox(width: 4),
            ],
          ],
        ),
      ),
    );
  }
}

/// What a manager should look at, from what the platform already computed.
///
/// The board's card was a FAT deviation against a rolling average. No read
/// exposes that — there is no deviation or signal endpoint — so it is not
/// drawn, and neither is the intelligence tone that belonged to it: that hue
/// exists to mark a COMPUTED signal, and using it for a platform fact would
/// spend the one colour reserved for something this product does not yet do.
/// What IS here is real: the readiness checks the platform failed, and the
/// collections it could not price.
class _NeedsALook extends StatelessWidget {
  const _NeedsALook({
    required this.l,
    required this.readiness,
    required this.unpriced,
  });

  final L10n l;
  final ReadinessResultView? readiness;
  final int unpriced;

  @override
  Widget build(BuildContext context) {
    final failed =
        readiness?.checks.where((c) => !c.passed).toList() ??
        const <ReadinessCheckView>[];
    final items = <Widget>[
      if (unpriced > 0)
        _LookRow(
          title: l.t('manager.unpriced', {'count': unpriced}),
          detail: l.t('manager.unpricedDetail'),
        ),
      for (final check in failed)
        _LookRow(
          title: check.rule.replaceAll(RegExp(r'[_.]'), ' '),
          detail: check.detail,
        ),
    ];
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionLabel(text: l.t('manager.needsALook')),
          const SizedBox(height: 10),
          if (items.isEmpty)
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: 16,
                vertical: 14,
              ),
              decoration: BoxDecoration(
                color: LactevaColors.milk,
                border: Border.all(color: LactevaColors.hairline),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Text(
                l.t('manager.allClear'),
                style: const TextStyle(
                  fontSize: 13.5,
                  color: LactevaColors.muted,
                ),
              ),
            ),
          for (final item in items)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: item,
            ),
        ],
      ),
    );
  }
}

class _LookRow extends StatelessWidget {
  const _LookRow({required this.title, required this.detail});

  final String title;
  final String detail;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: LactevaColors.milk,
        border: Border.all(color: LactevaColors.warningHairline),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: LactevaColors.warningTint,
              borderRadius: BorderRadius.circular(11),
            ),
            child: const Icon(
              Icons.warning_amber_rounded,
              size: 19,
              color: LactevaColors.warning,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 14.5,
                    fontWeight: FontWeight.w600,
                    color: LactevaColors.ink,
                  ),
                ),
                if (detail.isNotEmpty) ...[
                  const SizedBox(height: 1),
                  Text(
                    detail,
                    style: const TextStyle(
                      fontSize: 12.5,
                      color: LactevaColors.muted,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
