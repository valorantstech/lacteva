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
    final tabs = tabsFor(
      widget.session,
    ).where((t) => widget.roots.containsKey(t.key)).toList();
    if (tabs.length < 2) {
      // A bar of one tab is no bar: the root stands alone, exactly as before.
      final only = tabs.isEmpty
          ? widget.roots.values.first
          : widget.roots[tabs.first.key]!;
      return Builder(builder: only);
    }
    final index = _index.clamp(0, tabs.length - 1);
    return Scaffold(
      body: IndexedStack(
        index: index,
        children: [
          for (final tab in tabs) Builder(builder: widget.roots[tab.key]!),
        ],
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
            : ResolutionTestScreen(
                client: client,
                centerId: centre.id,
                session: session,
              );
      case 'todaySummary':
        return centre == null
            ? null
            : CenterTodayScreen(
                client: client,
                centerId: centre.id,
                session: session,
              );
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
            : CenterDetailScreen(
                client: client,
                centerId: centre.id,
                session: session,
              );
      case 'readiness':
        return centre == null
            ? null
            : ReadinessScreen(
                client: client,
                centerId: centre.id,
                session: session,
              );
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
    final visible = widget.items
        .where((i) => i.visibleFor(widget.session))
        .toList();
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
                    subtitle: blocked && !_resolving
                        ? Text(l.t('hub.noCentre'))
                        : null,
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

/// The household's bills, as a tab (WO-86): the month at a glance from the
/// platform's own statement, then EVERY invoice ever issued, a page at a
/// time, each opening the bill screen that already existed.
///
/// Nothing here is computed. The opening/billed/paid/closing figures are the
/// statement's — the same four the dairy's portal shows — and paging asks the
/// platform for the next page rather than fetching everything and slicing.
class CustomerBillsScreen extends StatefulWidget {
  const CustomerBillsScreen({
    super.key,
    required this.client,
    required this.session,
  });

  final ApiClient client;
  final Session session;

  /// One page. Small enough for a household with years of history to open
  /// the tab quickly; the button at the foot asks for the rest.
  static const int pageSize = 24;

  @override
  State<CustomerBillsScreen> createState() => _CustomerBillsScreenState();
}

class _CustomerBillsScreenState extends State<CustomerBillsScreen> {
  List<Map<String, dynamic>>? _bills;
  int _total = 0;
  Map<String, dynamic>? _statement;
  bool _loadingMore = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final page = await widget.client.listInvoices(
        limit: CustomerBillsScreen.pageSize,
      );
      final items = ((page['items'] as List<dynamic>?) ?? const [])
          .map((e) => (e as Map).cast<String, dynamic>())
          .toList();
      Map<String, dynamic>? statement;
      final customerId = widget.session.customerId;
      if (customerId != null) {
        try {
          statement = await widget.client.customerStatement(customerId);
        } catch (_) {
          // The statement is the summary, not the list: the bills still show.
          statement = null;
        }
      }
      if (!mounted) return;
      setState(() {
        _bills = items;
        _total = (page['total'] as num?)?.toInt() ?? items.length;
        _statement = statement;
      });
    } catch (_) {
      if (mounted) {
        setState(
          () => _error = L10n.of(widget.session).t('common.couldNotReach'),
        );
      }
    }
  }

  Future<void> _more() async {
    final have = _bills?.length ?? 0;
    setState(() => _loadingMore = true);
    try {
      final page = await widget.client.listInvoices(
        limit: CustomerBillsScreen.pageSize,
        offset: have,
      );
      final items = ((page['items'] as List<dynamic>?) ?? const [])
          .map((e) => (e as Map).cast<String, dynamic>())
          .toList();
      if (!mounted) return;
      setState(() {
        _bills = [...?_bills, ...items];
        _total = (page['total'] as num?)?.toInt() ?? _total;
      });
    } catch (_) {
      // Leave what is shown; the button stays for another try.
    } finally {
      if (mounted) setState(() => _loadingMore = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = L10n.of(widget.session);
    final bills = _bills;
    final statement = _statement;
    final more = bills != null && bills.length < _total;
    return Scaffold(
      appBar: AppBar(title: Text(l.t('nav.bill'))),
      body: _error != null
          ? Center(child: Text(_error!))
          : bills == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                if (statement != null)
                  Card(
                    key: const ValueKey('bills-statement'),
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            l.t('customer.statementTitle'),
                            style: Theme.of(context).textTheme.labelLarge,
                          ),
                          const SizedBox(height: 4),
                          Text(
                            '${statement['date_from'] ?? ''} → ${statement['date_to'] ?? ''}',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                          const SizedBox(height: 12),
                          _StatementRow(
                            l.t('customer.opening'),
                            money(statement['opening_balance'], widget.session),
                          ),
                          _StatementRow(
                            l.t('customer.billedLabel'),
                            money(statement['billed'], widget.session),
                          ),
                          _StatementRow(
                            l.t('customer.paid'),
                            money(statement['paid'], widget.session),
                          ),
                          const Divider(),
                          _StatementRow(
                            l.t('customer.closing'),
                            money(statement['closing_balance'], widget.session),
                            bold: true,
                            valueKey: const ValueKey('bills-closing'),
                          ),
                        ],
                      ),
                    ),
                  ),
                if (bills.isEmpty)
                  Padding(
                    padding: const EdgeInsets.all(24),
                    child: Center(child: Text(l.t('hub.noBills'))),
                  ),
                for (final bill in bills)
                  Card(
                    key: ValueKey('bill-row-${bill['id']}'),
                    child: ListTile(
                      title: Text('${bill['invoice_number'] ?? bill['id']}'),
                      subtitle: Text(
                        '${businessDate(bill['period_from']?.toString())} → '
                        '${businessDate(bill['period_to']?.toString())} · '
                        '${l.t('invoice.${bill['status']}')}',
                      ),
                      trailing: Text(
                        money(
                          bill['amount_due'] ?? bill['total'],
                          widget.session,
                        ),
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
                if (more)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: OutlinedButton(
                      key: const ValueKey('bills-more'),
                      onPressed: _loadingMore ? null : _more,
                      child: Text(l.t('customer.loadMore')),
                    ),
                  )
                else if (bills.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    child: Center(
                      child: Text(
                        l.t('customer.allLoaded'),
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                  ),
              ],
            ),
    );
  }
}

class _StatementRow extends StatelessWidget {
  const _StatementRow(
    this.label,
    this.value, {
    this.bold = false,
    this.valueKey,
  });

  final String label;
  final String value;
  final bool bold;
  final Key? valueKey;

  @override
  Widget build(BuildContext context) {
    final style = bold
        ? Theme.of(
            context,
          ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)
        : Theme.of(context).textTheme.bodyMedium;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(child: Text(label, style: style)),
          const SizedBox(width: 12),
          Text(value, key: valueKey, style: style),
        ],
      ),
    );
  }
}
