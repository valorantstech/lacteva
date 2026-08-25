import 'package:flutter/material.dart';

import 'api.dart';
import 'center_summary.dart';
import 'collection_wizard.dart';
import 'home.dart';
import 'l10n.dart';
import 'notifications.dart';
import 'session.dart';
import 'offline/offline_client.dart';
import 'offline/sync_screen.dart';
import 'payments.dart';
import 'receipts.dart';
import 'pricing_resolution.dart';
import 'rate_cards.dart';
import 'settlements.dart';
import 'sign_out.dart';
import 'suppliers.dart';
import 'transactions_history.dart';

/// Login screen — SPRINT-003: first real auth flow in the mobile app.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.client, this.notice});

  /// DEMO-012: the OFFLINE client specifically. Sign-in leads to the delivery
  /// round, which captures into the durable queue — so the type that carries
  /// that queue has to reach it. Widening this to `ApiClient` would compile
  /// and then drop a rider's round on the first tunnel.
  final OfflineApiClient client;

  /// Why the person is looking at this screen again, when there is a reason —
  /// "Your session expired — sign in again" (P0-PRODUCT-008 D-2). Shown in
  /// the same slot as an error, because it answers the same question.
  final String? notice;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  String? _error;
  bool _busy = false;

  /// Captured work waiting on this phone (P1-MOBILE-COUNTER-001 §5). After a
  /// restart while offline the operator cannot sign in — but they CAN be told
  /// their morning's work is safe in the durable queue and will sync after
  /// sign-in. Visibility without authentication reveals only a count.
  int _queuedOffline = 0;

  @override
  void initState() {
    super.initState();
    _error = widget.notice;
    widget.client.queue
        .load()
        .then((_) {
          if (mounted) {
            setState(() => _queuedOffline = widget.client.pendingCount);
          }
        })
        .catchError((_) {});
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      // DEMO-010 made the platform resolve the organization from the
      // credentials, so a dairy worker no longer types a UUID to sign in.
      // The field is gone; the parameter stays for the rare account that
      // exists in two organizations.
      await widget.client.login(_email.text.trim(), _password.text);
      if (!mounted) return;
      // DEMO-012: the PLATFORM decides where this lands, not this screen.
      // It used to push the collection-centre list at everybody — including
      // a household, who then met a wall of 403s on a screen about somebody
      // else's milk.
      await Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => HomeRouter(client: widget.client)),
      );
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } catch (_) {
      setState(() => _error = L10n.of(null).t('common.couldNotReach'));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    // Nobody is signed in yet, so there is no session to carry a locale —
    // English today, translatable the day a pre-auth locale source is chosen
    // (P1-LOCALE-I18N-001).
    final t = L10n.of(null);
    return Scaffold(
      appBar: AppBar(title: const Text('Lacteva — Sign in')),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (_queuedOffline > 0)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 16),
                      child: Card(
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Text(
                            t.t('login.queuedSafe', {'count': _queuedOffline}),
                          ),
                        ),
                      ),
                    ),
                  TextFormField(
                    controller: _email,
                    decoration: InputDecoration(labelText: t.t('auth.email')),
                    keyboardType: TextInputType.emailAddress,
                    validator: (v) => (v == null || !v.contains('@'))
                        ? 'Enter your email'
                        : null,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _password,
                    decoration: InputDecoration(
                      labelText: t.t('auth.password'),
                    ),
                    obscureText: true,
                    validator: (v) =>
                        (v == null || v.isEmpty) ? 'Enter your password' : null,
                  ),
                  const SizedBox(height: 20),
                  if (_error != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(
                        _error!,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ),
                  FilledButton(
                    onPressed: _busy ? null : _submit,
                    child: Text(
                      _busy ? t.t('auth.signingIn') : t.t('auth.signIn'),
                    ),
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

/// Paginated, searchable list of collection centers.
class CentersListScreen extends StatefulWidget {
  const CentersListScreen({super.key, required this.client, this.session});

  final ApiClient client;

  /// The signed-in principal, for language only (P1-LOCALE-I18N-001).
  /// Null renders English — no test constructor changes needed.
  final Session? session;

  @override
  State<CentersListScreen> createState() => _CentersListScreenState();
}

class _CentersListScreenState extends State<CentersListScreen> {
  static const pageSize = 20;
  final _search = TextEditingController();
  CenterPage? _page;
  int _offset = 0;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final page = await widget.client.listCenters(
        query: _search.text.trim(),
        limit: pageSize,
        offset: _offset,
      );
      if (!mounted) return;
      setState(() {
        _page = page;
        _error = null;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.detail);
    } catch (_) {
      // A transport failure is not a platform refusal (P0-PRODUCT-008 D-1):
      // say so instead of leaving the spinner forever.
      if (mounted) {
        setState(
          () => _error = L10n.of(widget.session).t('common.couldNotReach'),
        );
      }
    }
  }

  Future<void> _openForm({CenterSummary? center}) async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => CenterFormScreen(
          client: widget.client,
          center: center,
          session: widget.session,
        ),
      ),
    );
    if (changed == true) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final page = _page;
    final t = L10n.of(widget.session);
    return Scaffold(
      appBar: AppBar(
        title: Text(t.t('center.listTitle')),
        actions: [
          SignOutButton(client: widget.client, label: t.t('common.signOut')),
          IconButton(
            icon: const Icon(Icons.people_outline),
            tooltip: t.t('supplier.title'),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => SuppliersListScreen(
                  client: widget.client,
                  session: widget.session,
                ),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.price_change_outlined),
            tooltip: t.t('center.rateCards'),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => RateCardsListScreen(client: widget.client),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.receipt_long_outlined),
            tooltip: t.t('center.settlements'),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => SettlementListScreen(client: widget.client),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.payments_outlined),
            tooltip: t.t('center.payments'),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => PaymentHistoryScreen(client: widget.client),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.sync),
            tooltip: t.t('sync.title'),
            onPressed: () {
              final client = widget.client;
              if (client is! OfflineApiClient) return;
              Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => SyncStatusScreen(
                    client: client,
                    session: widget.session,
                  ),
                ),
              );
            },
          ),
          IconButton(
            icon: const Icon(Icons.receipt_long_outlined),
            tooltip: t.t('center.receipts'),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => ReceiptHistoryScreen(client: widget.client),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.notifications_none),
            tooltip: t.t('center.notifications'),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) =>
                    NotificationHistoryScreen(client: widget.client),
              ),
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _openForm(),
        tooltip: t.t('center.new'),
        child: const Icon(Icons.add),
      ),
      body: Column(
        children: [
          if (widget.client is OfflineApiClient)
            OfflineBanner(
              client: widget.client as OfflineApiClient,
              session: widget.session,
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => SyncStatusScreen(
                    client: widget.client as OfflineApiClient,
                    session: widget.session,
                  ),
                ),
              ),
            ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  TextField(
                    controller: _search,
                    decoration: InputDecoration(
                      prefixIcon: const Icon(Icons.search),
                      hintText: t.t('center.searchHint'),
                    ),
                    onSubmitted: (_) {
                      _offset = 0;
                      _load();
                    },
                  ),
                  const SizedBox(height: 12),
                  if (_error != null)
                    Text(
                      _error!,
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                  if (page == null && _error == null)
                    const Padding(
                      padding: EdgeInsets.all(32),
                      child: Center(child: CircularProgressIndicator()),
                    ),
                  if (page != null && page.items.isEmpty)
                    Padding(
                      padding: const EdgeInsets.all(32),
                      child: Center(child: Text(t.t('center.noneMatch'))),
                    ),
                  if (page != null)
                    ...page.items.map(
                      (c) => Card(
                        child: ListTile(
                          title: Text(c.name),
                          subtitle: Text(c.code),
                          leading: StatusChip(status: c.status),
                          trailing: IconButton(
                            icon: const Icon(Icons.edit_outlined),
                            tooltip: t.t('common.edit'),
                            onPressed: () => _openForm(center: c),
                          ),
                          onTap: () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => CenterDetailScreen(
                                client: widget.client,
                                centerId: c.id,
                                session: widget.session,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  if (page != null && page.total > pageSize)
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        TextButton(
                          onPressed: _offset == 0
                              ? null
                              : () {
                                  _offset = (_offset - pageSize).clamp(
                                    0,
                                    1 << 30,
                                  );
                                  _load();
                                },
                          child: Text(t.t('common.previous')),
                        ),
                        Text(
                          '${(_offset ~/ pageSize) + 1} / ${(page.total / pageSize).ceil()}',
                        ),
                        TextButton(
                          onPressed: _offset + pageSize >= page.total
                              ? null
                              : () {
                                  _offset += pageSize;
                                  _load();
                                },
                          child: Text(t.t('common.next')),
                        ),
                      ],
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final color = switch (status) {
      'active' => Colors.green,
      'maintenance' => Colors.orange,
      'archived' => Colors.grey,
      _ => Colors.blueGrey,
    };
    return CircleAvatar(radius: 6, backgroundColor: color);
  }
}

/// Create (branch + name + code) or edit (name + timezone) a center.
class CenterFormScreen extends StatefulWidget {
  const CenterFormScreen({
    super.key,
    required this.client,
    this.center,
    this.session,
  });

  final ApiClient client;
  final CenterSummary? center;

  /// For language only (P1-LOCALE-I18N-001); null renders English.
  final Session? session;

  bool get isEdit => center != null;

  @override
  State<CenterFormScreen> createState() => _CenterFormScreenState();
}

class _CenterFormScreenState extends State<CenterFormScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _name = TextEditingController(
    text: widget.center?.name ?? '',
  );
  late final TextEditingController _code = TextEditingController(
    text: widget.center?.code ?? '',
  );
  late final TextEditingController _timezone = TextEditingController(
    text: widget.center?.timezone ?? 'UTC',
  );
  List<BranchSummary> _branches = const [];
  String? _branchId;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    if (!widget.isEdit) {
      widget.client
          .listBranches()
          .then((branches) {
            if (!mounted) return;
            setState(() {
              _branches = branches;
              _branchId = branches.isEmpty ? null : branches.first.id;
            });
          })
          .catchError((_) {});
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (widget.isEdit) {
        await widget.client.updateCenter(
          widget.center!.id,
          name: _name.text.trim(),
          timezone: _timezone.text.trim(),
        );
      } else {
        await widget.client.createCenter(
          branchId: _branchId!,
          name: _name.text.trim(),
          code: _code.text.trim(),
        );
      }
      if (mounted) Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } catch (_) {
      // P1-PRODUCT-READINESS-001 R-1: a transport failure is not a platform
      // refusal. Without this the save silently did nothing — the busy flag
      // cleared, no message appeared, and the operator could reasonably
      // conclude the record had been saved. The load paths gained this in
      // P0-PRODUCT-009; the save paths are a different shape and were missed.
      setState(() => _error = L10n.of(null).t('common.couldNotReach'));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = L10n.of(widget.session);
    return Scaffold(
      appBar: AppBar(
        title: Text(
          widget.isEdit
              ? t.t('center.editTitle', {'code': widget.center!.code})
              : t.t('center.newTitle'),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (!widget.isEdit)
                DropdownButtonFormField<String>(
                  initialValue: _branchId,
                  decoration: InputDecoration(
                    labelText: t.t('center.branch'),
                  ),
                  items: _branches
                      .map(
                        (b) => DropdownMenuItem(
                          value: b.id,
                          child: Text('${b.code} — ${b.name}'),
                        ),
                      )
                      .toList(),
                  onChanged: (v) => setState(() => _branchId = v),
                  validator: (v) =>
                      v == null ? t.t('center.selectBranch') : null,
                ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _name,
                decoration: InputDecoration(labelText: t.t('center.name')),
                validator: (v) => (v == null || v.trim().length < 2)
                    ? t.t('common.nameTooShort')
                    : null,
              ),
              const SizedBox(height: 12),
              if (!widget.isEdit)
                TextFormField(
                  controller: _code,
                  decoration: InputDecoration(
                    labelText: t.t('center.code'),
                    helperText: t.t('center.codeHelp'),
                  ),
                  validator: (v) => (v == null || v.trim().isEmpty)
                      ? t.t('center.codeRequired')
                      : null,
                )
              else
                TextFormField(
                  controller: _timezone,
                  decoration: InputDecoration(
                    labelText: t.t('center.timezone'),
                  ),
                  validator: (v) => (v == null || v.trim().isEmpty)
                      ? t.t('common.required')
                      : null,
                ),
              const SizedBox(height: 20),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(
                    _error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: Text(
                  _busy ? t.t('common.saving') : t.t('common.save'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Read-only detail: status actions, operating hours, calendar, settings.
class CenterDetailScreen extends StatefulWidget {
  const CenterDetailScreen({
    super.key,
    required this.client,
    required this.centerId,
    this.session,
  });

  final ApiClient client;
  final String centerId;

  /// For language only (P1-LOCALE-I18N-001); null renders English.
  final Session? session;

  @override
  State<CenterDetailScreen> createState() => _CenterDetailScreenState();
}

class _CenterDetailScreenState extends State<CenterDetailScreen> {
  L10n get _l => L10n.of(widget.session);

  CenterDetail? _detail;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final detail = await widget.client.centerDetail(widget.centerId);
      if (mounted) {
        setState(() {
          _detail = detail;
          _error = null;
        });
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.detail);
    } catch (_) {
      // A transport failure is not a platform refusal (P0-PRODUCT-008 D-1):
      // say so instead of leaving the spinner forever.
      if (mounted) setState(() => _error = _l.t('common.couldNotReach'));
    }
  }

  /// End the shift (P1-MOBILE-COUNTER-001): find the centre's open session,
  /// ask — closing is a business act, the queue of that shift's collections
  /// is unaffected — then let the PLATFORM close it. Its refusal (a session
  /// with in-progress transactions, somebody else's session) renders
  /// verbatim.
  Future<void> _closeOpenSession(BuildContext context) async {
    final t = _l;
    try {
      final sessions = await widget.client.listOpenSessions(widget.centerId);
      if (!context.mounted) return;
      if (sessions.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(t.t('center.noOpenSession'))),
        );
        return;
      }
      final session = sessions.first;
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text(t.t('center.closeSessionTitle')),
          content: Text(
            t.t('center.closeSessionBody', {
              'label': session['label'] ?? session['id'],
            }),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: Text(t.t('center.keepOpen')),
            ),
            FilledButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: Text(t.t('center.closeSession')),
            ),
          ],
        ),
      );
      if (confirmed != true || !context.mounted) return;
      await widget.client.closeCollectionSession(session['id'] as String);
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(t.t('center.sessionClosed'))),
      );
    } on ApiException catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(e.detail)));
    } catch (_) {
      // Transport failure ≠ refusal (P0-PRODUCT-008 D-1).
      if (!context.mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(t.t('common.couldNotReach'))));
    }
  }

  Future<void> _setStatus(String status) async {
    try {
      await widget.client.setStatus(widget.centerId, status);
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
      ).showSnackBar(SnackBar(content: Text(_l.t('common.couldNotReach'))));
    }
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    final t = _l;
    return Scaffold(
      appBar: AppBar(
        title: Text(detail?.center.name ?? t.t('center.fallback')),
        actions: [
          // P1-MOBILE-COUNTER-001: the centre's collection history — the
          // phone's answer to a farmer's dispute at the counter.
          IconButton(
            icon: const Icon(Icons.history),
            tooltip: t.t('center.collections'),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => TransactionHistoryScreen(
                  client: widget.client,
                  centerId: widget.centerId,
                  centerName: detail?.center.name ?? t.t('center.fallback'),
                  session: widget.session,
                ),
              ),
            ),
          ),
          // P1-MOBILE-COUNTER-001 (audit D-12): end-of-shift session close —
          // the platform endpoint existed with no caller on any client.
          IconButton(
            icon: const Icon(Icons.event_busy_outlined),
            tooltip: t.t('center.closeSession'),
            onPressed: () => _closeOpenSession(context),
          ),
          IconButton(
            icon: const Icon(Icons.local_drink_outlined),
            tooltip: t.t('center.collectMilk'),
            onPressed: () async {
              try {
                final sessions = await widget.client.listOpenSessions(
                  widget.centerId,
                );
                final session = sessions.isNotEmpty
                    ? sessions.first
                    : await widget.client.openCollectionSession(
                        widget.centerId,
                      );
                if (!context.mounted) return;
                await Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => CollectionWizardScreen(
                      client: widget.client,
                      sessionId: session['id'] as String,
                      session: widget.session,
                    ),
                  ),
                );
              } on ApiException catch (e) {
                if (!context.mounted) return;
                ScaffoldMessenger.of(
                  context,
                ).showSnackBar(SnackBar(content: Text(e.detail)));
              } catch (_) {
                // Transport failure ≠ refusal (P0-PRODUCT-008 D-1).
                if (!context.mounted) return;
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(t.t('common.couldNotReach'))),
                );
              }
            },
          ),
          IconButton(
            icon: const Icon(Icons.fact_check_outlined),
            tooltip: t.t('readiness.title'),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => ReadinessScreen(
                  client: widget.client,
                  centerId: widget.centerId,
                  session: widget.session,
                ),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.insights_outlined),
            tooltip: t.t('center.todaySummary'),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => CenterTodayScreen(
                  client: widget.client,
                  centerId: widget.centerId,
                  session: widget.session,
                ),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.calculate_outlined),
            tooltip: t.t('center.pricingTest'),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => ResolutionTestScreen(
                  client: widget.client,
                  centerId: widget.centerId,
                  session: widget.session,
                ),
              ),
            ),
          ),
        ],
      ),
      body: detail == null
          ? Center(
              child: _error != null
                  ? Text(_error!)
                  : const CircularProgressIndicator(),
            )
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  child: ListTile(
                    leading: StatusChip(status: detail.center.status),
                    title: Text(detail.center.code),
                    subtitle: Text(
                      '${detail.center.status} · ${detail.center.timezone ?? t.t('center.orgTimezone')}',
                    ),
                  ),
                ),
                if (detail.center.status != 'archived')
                  Wrap(
                    spacing: 8,
                    children: [
                      if (detail.center.status != 'active')
                        FilledButton.tonal(
                          onPressed: () => _setStatus('active'),
                          child: Text(t.t('common.activate')),
                        ),
                      if (detail.center.status == 'active')
                        FilledButton.tonal(
                          onPressed: () => _setStatus('inactive'),
                          child: Text(t.t('center.deactivate')),
                        ),
                      if (detail.center.status != 'maintenance')
                        OutlinedButton(
                          onPressed: () => _setStatus('maintenance'),
                          child: Text(t.t('center.maintenance')),
                        ),
                    ],
                  ),
                const SizedBox(height: 16),
                Text(
                  t.t('center.hours'),
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                if (detail.windows.isEmpty)
                  ListTile(
                    dense: true,
                    title: Text(t.t('center.noHours')),
                  ),
                ...detail.windows.map(
                  (w) => ListTile(
                    dense: true,
                    leading: const Icon(Icons.schedule),
                    title: Text(w.label),
                  ),
                ),
                const SizedBox(height: 16),
                Text(
                  t.t('center.calendar'),
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                if (detail.calendar.isEmpty)
                  ListTile(dense: true, title: Text(t.t('center.noEntries'))),
                ...detail.calendar.map(
                  (e) => ListTile(
                    dense: true,
                    leading: const Icon(Icons.event),
                    title: Text('${e['day']} — ${e['kind']}'),
                    subtitle: (e['note'] as String?)?.isNotEmpty == true
                        ? Text(e['note'] as String)
                        : null,
                  ),
                ),
              ],
            ),
    );
  }
}

/// Operational readiness evaluation for one center (SPRINT-004).
class ReadinessScreen extends StatefulWidget {
  const ReadinessScreen({
    super.key,
    required this.client,
    required this.centerId,
    this.session,
  });

  final ApiClient client;
  final String centerId;

  /// For language only (P1-LOCALE-I18N-001); null renders English.
  final Session? session;

  @override
  State<ReadinessScreen> createState() => _ReadinessScreenState();
}

class _ReadinessScreenState extends State<ReadinessScreen> {
  ReadinessResultView? _result;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final result = await widget.client.readiness(widget.centerId);
      if (mounted) {
        setState(() {
          _result = result;
          _error = null;
        });
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.detail);
    } catch (_) {
      // A transport failure is not a platform refusal (P0-PRODUCT-008 D-1):
      // say so instead of leaving the spinner forever.
      if (mounted) {
        setState(
          () => _error = L10n.of(widget.session).t('common.couldNotReach'),
        );
      }
    }
  }

  Color _statusColor(String status) => switch (status) {
    'READY' => Colors.green,
    'WARNING' => Colors.orange,
    _ => Colors.red,
  };

  @override
  Widget build(BuildContext context) {
    final result = _result;
    final t = L10n.of(widget.session);
    return Scaffold(
      appBar: AppBar(title: Text(t.t('readiness.title'))),
      body: RefreshIndicator(
        onRefresh: _load,
        child: result == null
            ? Center(
                child: _error != null
                    ? Text(_error!)
                    : const CircularProgressIndicator(),
              )
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Card(
                    color: _statusColor(result.status).withValues(alpha: 0.12),
                    child: ListTile(
                      leading: Icon(
                        result.status == 'READY'
                            ? Icons.check_circle
                            : result.status == 'WARNING'
                            ? Icons.warning_amber
                            : Icons.cancel,
                        color: _statusColor(result.status),
                        size: 36,
                      ),
                      title: Text(
                        result.status,
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      subtitle: Text(
                        t.t('readiness.checksPassing', {
                          'passed': result.checks
                              .where((c) => c.passed)
                              .length,
                          'total': result.checks.length,
                        }),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  ...result.checks.map(
                    (check) => ListTile(
                      leading: Icon(
                        check.passed
                            ? Icons.check_circle_outline
                            : Icons.error_outline,
                        color: check.passed
                            ? Colors.green
                            : (check.severity == 'blocking'
                                  ? Colors.red
                                  : Colors.orange),
                      ),
                      title: Text(check.rule),
                      subtitle: Text(check.detail),
                      trailing: Text(check.severity),
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}
