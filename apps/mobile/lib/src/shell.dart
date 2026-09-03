/// The persistent bottom bar and the hub tabs behind it (WO-72 Part B).
///
/// [AppShell] wraps an experience's root in a Scaffold whose bottom bar is
/// the tab set [tabsFor] chose for this session — shaped by experience,
/// filtered by capability. Each tab's root is built once and kept in an
/// [IndexedStack], so switching tabs does not refetch what a tab already
/// loaded and does not lose a half-typed search.
///
/// The hubs — Money, Reports, More, and the operator's Today — are lists of
/// the screens that already existed and were only reachable by drilling.
/// They build nothing new; they say where things are. A hub item the
/// session cannot open is absent, not disabled (P0-UX-001: a greyed control
/// tells a person the capability exists and they are not trusted with it).
///
/// DS V1.1: the bar takes the theme's surface and hairline and the product's
/// own green for the selected item; nothing here invents a token.
library;

import 'package:flutter/material.dart';

import 'api.dart';
import 'center_summary.dart';
import 'centers.dart';
import 'collection_home.dart';
import 'deliveries.dart';
import 'customer_portal.dart';
import 'devices/binding_store.dart';
import 'devices/instruments_screen.dart';
import 'l10n.dart';
import 'navigation.dart';
import 'notifications.dart';
import 'offline/offline_client.dart';
import 'offline/sync_screen.dart';
import 'payments.dart';
import 'pricing_matrices.dart';
import 'pricing_resolution.dart';
import 'rate_cards.dart';
import 'receipts.dart';
import 'session.dart';
import 'settlements.dart';
import 'sign_out.dart';
import 'theme.dart';
import 'transactions_history.dart';

class AppShell extends StatefulWidget {
  const AppShell({
    super.key,
    required this.client,
    required this.session,
    required this.roots,
    this.initialTab = 0,
  });

  final ApiClient client;
  final Session session;

  /// Tab key → the widget that tab shows. A tab with no root here is not
  /// rendered even if the capability check passed — the map is the truth.
  final Map<String, WidgetBuilder> roots;
  final int initialTab;

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  late int _index = widget.initialTab;

  @override
  Widget build(BuildContext context) {
    final l = L10n.of(widget.session);
    final tabs = tabsFor(widget.session).where((t) => widget.roots.containsKey(t.key)).toList();
    if (tabs.length < 2) {
      // A bar of one tab is no bar: the root stands alone, exactly as before.
      final only = tabs.isEmpty ? widget.roots.values.first : widget.roots[tabs.first.key]!;
      return Builder(builder: only);
    }
    final index = _index.clamp(0, tabs.length - 1);
    return Scaffold(
      body: IndexedStack(
        index: index,
        children: [for (final tab in tabs) Builder(builder: widget.roots[tab.key]!)],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (i) => setState(() => _index = i),
        backgroundColor: LactevaColors.milk,
        indicatorColor: LactevaColors.dairy.withValues(alpha: 0.14),
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        destinations: [
          for (final tab in tabs)
            NavigationDestination(
              key: ValueKey('nav-${tab.key}'),
              icon: Icon(tab.icon),
              selectedIcon: Icon(tab.selectedIcon, color: LactevaColors.dairy),
              label: l.t(tab.labelKey),
            ),
        ],
      ),
    );
  }
}

/// Which centre this person works at, resolved once for the hubs that need
/// one — the same rule the dashboard uses: the first active centre inside
/// the session's scope.
Future<CenterSummary?> resolveCentre(ApiClient client, Session session) async {
  final page = await client.listCenters(limit: 20, status: 'active');
  final mine = page.items.where((c) => session.coversCenter(c.id)).toList();
  return mine.isEmpty ? null : mine.first;
}

/// A hub: the screens a tab holds, as a list a thumb can read.
class HubScreen extends StatefulWidget {
  const HubScreen({
    super.key,
    required this.client,
    required this.session,
    required this.titleKey,
    required this.items,
    this.signOut = false,
  });

  final ApiClient client;
  final Session session;
  final String titleKey;
  final List<HubItem> items;

  /// The More hub carries the way out of a shared handset.
  final bool signOut;

  @override
  State<HubScreen> createState() => _HubScreenState();
}

class _HubScreenState extends State<HubScreen> {
  CenterSummary? _centre;
  bool _resolving = true;

  L10n get _l => L10n.of(widget.session);

  @override
  void initState() {
    super.initState();
    if (widget.items.any((i) => i.needsCentre)) {
      resolveCentre(widget.client, widget.session)
          .then((c) {
            if (mounted) setState(() => _centre = c);
          })
          .catchError((_) {})
          .whenComplete(() {
            if (mounted) setState(() => _resolving = false);
          });
    } else {
      _resolving = false;
    }
  }

  void _open(Widget screen) =>
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));

  /// Every hub destination, by key. Adding a screen means adding it here AND
  /// to `screenHomes`; the test holds both to account.
  Widget? _screenFor(HubItem item) {
    final client = widget.client;
    final session = widget.session;
    final centre = _centre;
    switch (item.key) {
      case 'settlements':
        return SettlementListScreen(client: client);
      case 'payments':
        return PaymentHistoryScreen(client: client);
      case 'receipts':
        return ReceiptHistoryScreen(client: client);
      case 'rateCards':
        return RateCardsListScreen(client: client);
      case 'matrices':
        return MatrixListScreen(client: client);
      case 'rateTest':
        return centre == null
            ? null
            : ResolutionTestScreen(client: client, centerId: centre.id, session: session);
      case 'todaySummary':
        return centre == null
            ? null
            : CenterTodayScreen(client: client, centerId: centre.id, session: session);
      case 'transactions':
        return centre == null
            ? null
            : TransactionHistoryScreen(
                client: client,
                centerId: centre.id,
                centerName: centre.name,
                session: session,
              );
      case 'notifications':
        return NotificationHistoryScreen(client: client);
      case 'counter':
        // The counter and the round run offline-first; a plain client has
        // no queue to hand them, so the hub simply omits the row.
        final counter = client;
        if (counter is! OfflineApiClient) return null;
        return CollectionHomeScreen(client: counter, session: session);
      case 'round':
        final round = client;
        if (round is! OfflineApiClient) return null;
        return DeliveryRoundScreen(client: round, session: session);
      case 'centres':
        return CentersListScreen(client: client, session: session);
      case 'centreCalendar':
        return centre == null
            ? null
            : CenterDetailScreen(client: client, centerId: centre.id, session: session);
      case 'readiness':
        return centre == null
            ? null
            : ReadinessScreen(client: client, centerId: centre.id, session: session);
      case 'instruments':
        final offline = client;
        if (centre == null || offline is! OfflineApiClient) return null;
        return InstrumentsScreen(
          client: offline,
          centerId: centre.id,
          bindings: BindingStore(offline.queue.store),
        );
      case 'sync':
        final offline = client;
        if (offline is! OfflineApiClient) return null;
        return SyncStatusScreen(client: offline, session: session);
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final l = _l;
    final visible = widget.items.where((i) => i.visibleFor(widget.session)).toList();
    return Scaffold(
      appBar: AppBar(title: Text(l.t(widget.titleKey))),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          for (final item in visible)
            Builder(
              builder: (context) {
                final needsCentre = item.needsCentre;
                final blocked = needsCentre && _centre == null;
                return Card(
                  margin: const EdgeInsets.only(bottom: 10),
                  child: ListTile(
                    key: ValueKey('hub-${item.key}'),
                    leading: Icon(item.icon, color: LactevaColors.dairy),
                    title: Text(l.t(item.labelKey)),
                    subtitle: blocked && !_resolving ? Text(l.t('hub.noCentre')) : null,
                    trailing: const Icon(Icons.chevron_right),
                    enabled: !blocked,
                    onTap: blocked
                        ? null
                        : () {
                            final screen = _screenFor(item);
                            if (screen != null) _open(screen);
                          },
                  ),
                );
              },
            ),
          if (widget.signOut) ...[
            const SizedBox(height: 8),
            _SignOutRow(client: widget.client, label: l.t('hub.signOut')),
          ],
        ],
      ),
    );
  }
}

class _SignOutRow extends StatelessWidget {
  const _SignOutRow({required this.client, required this.label});

  final ApiClient client;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        key: const ValueKey('hub-signOut'),
        leading: const Icon(Icons.logout, color: LactevaColors.muted),
        title: Text(label),
        trailing: SignOutButton(client: client, label: label),
      ),
    );
  }
}

/// The household's bills, as a tab: the invoices the platform lists, each
/// opening the bill it already had a screen for.
class CustomerBillsScreen extends StatefulWidget {
  const CustomerBillsScreen({super.key, required this.client, required this.session});

  final ApiClient client;
  final Session session;

  @override
  State<CustomerBillsScreen> createState() => _CustomerBillsScreenState();
}

class _CustomerBillsScreenState extends State<CustomerBillsScreen> {
  List<Map<String, dynamic>>? _bills;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final page = await widget.client.listInvoices(limit: 24);
      final items = ((page['items'] as List<dynamic>?) ?? const [])
          .map((e) => (e as Map).cast<String, dynamic>())
          .toList();
      if (mounted) setState(() => _bills = items);
    } catch (_) {
      if (mounted) setState(() => _error = L10n.of(widget.session).t('common.couldNotReach'));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = L10n.of(widget.session);
    final bills = _bills;
    return Scaffold(
      appBar: AppBar(title: Text(l.t('nav.bill'))),
      body: _error != null
          ? Center(child: Text(_error!))
          : bills == null
          ? const Center(child: CircularProgressIndicator())
          : bills.isEmpty
          ? Center(child: Text(l.t('hub.noBills')))
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                for (final bill in bills)
                  Card(
                    child: ListTile(
                      title: Text('${bill['invoice_number'] ?? bill['id']}'),
                      subtitle: Text('${bill['period_start'] ?? ''} → ${bill['period_end'] ?? ''}'),
                      trailing: Text(
                        money(bill['total_amount'] ?? bill['total'], widget.session),
                      ),
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => CustomerBillScreen(
                            client: widget.client,
                            invoiceId: bill['id'].toString(),
                            session: widget.session,
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
    );
  }
}
