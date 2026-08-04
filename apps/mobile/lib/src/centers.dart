import 'package:flutter/material.dart';

import 'api.dart';
import 'center_summary.dart';
import 'collection_wizard.dart';
import 'notifications.dart';
import 'offline/offline_client.dart';
import 'offline/sync_screen.dart';
import 'payments.dart';
import 'receipts.dart';
import 'pricing_resolution.dart';
import 'rate_cards.dart';
import 'settlements.dart';
import 'suppliers.dart';

/// Login screen — SPRINT-003: first real auth flow in the mobile app.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.client});

  final ApiClient client;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _tenant = TextEditingController();
  String? _error;
  bool _busy = false;

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.client.login(
        _email.text.trim(),
        _password.text,
        tenantId: _tenant.text.trim(),
      );
      if (!mounted) return;
      await Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => CentersListScreen(client: widget.client),
        ),
      );
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } catch (_) {
      setState(() => _error = 'Could not reach the platform');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
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
                  TextFormField(
                    controller: _email,
                    decoration: const InputDecoration(labelText: 'Email'),
                    keyboardType: TextInputType.emailAddress,
                    validator: (v) => (v == null || !v.contains('@'))
                        ? 'Enter your email'
                        : null,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _password,
                    decoration: const InputDecoration(labelText: 'Password'),
                    obscureText: true,
                    validator: (v) =>
                        (v == null || v.isEmpty) ? 'Enter your password' : null,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _tenant,
                    decoration: const InputDecoration(
                      labelText: 'Organization ID',
                      helperText: 'Optional — leave empty for platform login',
                    ),
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
                    child: Text(_busy ? 'Signing in…' : 'Sign in'),
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
  const CentersListScreen({super.key, required this.client});

  final ApiClient client;

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
    }
  }

  Future<void> _openForm({CenterSummary? center}) async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => CenterFormScreen(client: widget.client, center: center),
      ),
    );
    if (changed == true) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final page = _page;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Collection centers'),
        actions: [
          IconButton(
            icon: const Icon(Icons.people_outline),
            tooltip: 'Suppliers',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => SuppliersListScreen(client: widget.client),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.price_change_outlined),
            tooltip: 'Rate cards',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => RateCardsListScreen(client: widget.client),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.receipt_long_outlined),
            tooltip: 'Settlements',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => SettlementListScreen(client: widget.client),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.payments_outlined),
            tooltip: 'Payments',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => PaymentHistoryScreen(client: widget.client),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.sync),
            tooltip: 'Sync',
            onPressed: () {
              final client = widget.client;
              if (client is! OfflineApiClient) return;
              Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => SyncStatusScreen(client: client),
                ),
              );
            },
          ),
          IconButton(
            icon: const Icon(Icons.receipt_long_outlined),
            tooltip: 'Receipts',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => ReceiptHistoryScreen(client: widget.client),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.notifications_none),
            tooltip: 'Notifications',
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
        tooltip: 'New center',
        child: const Icon(Icons.add),
      ),
      body: Column(
        children: [
          if (widget.client is OfflineApiClient)
            OfflineBanner(
              client: widget.client as OfflineApiClient,
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => SyncStatusScreen(
                    client: widget.client as OfflineApiClient,
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
                    decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.search),
                      hintText: 'Search by name or code',
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
                    const Padding(
                      padding: EdgeInsets.all(32),
                      child: Center(child: Text('No centers match.')),
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
                            tooltip: 'Edit',
                            onPressed: () => _openForm(center: c),
                          ),
                          onTap: () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => CenterDetailScreen(
                                client: widget.client,
                                centerId: c.id,
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
                          child: const Text('Previous'),
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
                          child: const Text('Next'),
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
  const CenterFormScreen({super.key, required this.client, this.center});

  final ApiClient client;
  final CenterSummary? center;

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
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          widget.isEdit
              ? 'Edit ${widget.center!.code}'
              : 'New collection center',
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
                  decoration: const InputDecoration(labelText: 'Branch'),
                  items: _branches
                      .map(
                        (b) => DropdownMenuItem(
                          value: b.id,
                          child: Text('${b.code} — ${b.name}'),
                        ),
                      )
                      .toList(),
                  onChanged: (v) => setState(() => _branchId = v),
                  validator: (v) => v == null ? 'Select a branch' : null,
                ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _name,
                decoration: const InputDecoration(labelText: 'Name'),
                validator: (v) => (v == null || v.trim().length < 2)
                    ? 'Name needs at least 2 characters'
                    : null,
              ),
              const SizedBox(height: 12),
              if (!widget.isEdit)
                TextFormField(
                  controller: _code,
                  decoration: const InputDecoration(
                    labelText: 'Code',
                    helperText: 'Unique within your organization, e.g. KH-C1',
                  ),
                  validator: (v) => (v == null || v.trim().isEmpty)
                      ? 'Code is required'
                      : null,
                )
              else
                TextFormField(
                  controller: _timezone,
                  decoration: const InputDecoration(labelText: 'Timezone'),
                  validator: (v) =>
                      (v == null || v.trim().isEmpty) ? 'Required' : null,
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
                child: Text(_busy ? 'Saving…' : 'Save'),
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
  });

  final ApiClient client;
  final String centerId;

  @override
  State<CenterDetailScreen> createState() => _CenterDetailScreenState();
}

class _CenterDetailScreenState extends State<CenterDetailScreen> {
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
    }
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    return Scaffold(
      appBar: AppBar(
        title: Text(detail?.center.name ?? 'Center'),
        actions: [
          IconButton(
            icon: const Icon(Icons.local_drink_outlined),
            tooltip: 'Collect milk',
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
                    ),
                  ),
                );
              } on ApiException catch (e) {
                if (!context.mounted) return;
                ScaffoldMessenger.of(
                  context,
                ).showSnackBar(SnackBar(content: Text(e.detail)));
              }
            },
          ),
          IconButton(
            icon: const Icon(Icons.fact_check_outlined),
            tooltip: 'Operational readiness',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => ReadinessScreen(
                  client: widget.client,
                  centerId: widget.centerId,
                ),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.insights_outlined),
            tooltip: "Today's summary",
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => CenterTodayScreen(
                  client: widget.client,
                  centerId: widget.centerId,
                ),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.calculate_outlined),
            tooltip: 'Pricing resolution test',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => ResolutionTestScreen(
                  client: widget.client,
                  centerId: widget.centerId,
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
                      '${detail.center.status} · ${detail.center.timezone}',
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
                          child: const Text('Activate'),
                        ),
                      if (detail.center.status == 'active')
                        FilledButton.tonal(
                          onPressed: () => _setStatus('inactive'),
                          child: const Text('Deactivate'),
                        ),
                      if (detail.center.status != 'maintenance')
                        OutlinedButton(
                          onPressed: () => _setStatus('maintenance'),
                          child: const Text('Maintenance'),
                        ),
                    ],
                  ),
                const SizedBox(height: 16),
                Text(
                  'Operating hours',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                if (detail.windows.isEmpty)
                  const ListTile(
                    dense: true,
                    title: Text(
                      'No operating hours set — '
                      'the center cannot be activated yet.',
                    ),
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
                  'Business calendar',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                if (detail.calendar.isEmpty)
                  const ListTile(dense: true, title: Text('No entries.')),
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
  });

  final ApiClient client;
  final String centerId;

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
    return Scaffold(
      appBar: AppBar(title: const Text('Operational readiness')),
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
                        '${result.checks.where((c) => c.passed).length}'
                        ' of ${result.checks.length} checks passing',
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
