import 'package:flutter/material.dart';

import 'api.dart';

/// Settlement screens — SET-001 (lifecycle only, no payment).
class SettlementListScreen extends StatefulWidget {
  const SettlementListScreen({super.key, required this.client});

  final ApiClient client;

  @override
  State<SettlementListScreen> createState() => _SettlementListScreenState();
}

class _SettlementListScreenState extends State<SettlementListScreen> {
  static const pageSize = 20;
  final _search = TextEditingController();
  SettlementPageResult? _page;
  int _offset = 0;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final page = await widget.client.listSettlements(
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

  @override
  Widget build(BuildContext context) {
    final page = _page;
    return Scaffold(
      appBar: AppBar(title: const Text('Settlements')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextField(
              controller: _search,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Search by settlement number',
              ),
              onSubmitted: (_) {
                _offset = 0;
                _load();
              },
            ),
            const SizedBox(height: 12),
            if (_error != null)
              Text(_error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error)),
            if (page == null && _error == null)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: CircularProgressIndicator()),
              ),
            if (page != null && page.items.isEmpty)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: Text('No settlements yet.')),
              ),
            if (page != null)
              ...page.items.map(
                (s) => Card(
                  child: ListTile(
                    title: Text(s.number),
                    subtitle: Text('${s.periodFrom} → ${s.periodTo} · '
                        '${s.lineCount} line(s) · '
                        'net ${s.netAmount} ${s.currency}'),
                    trailing: Chip(
                      label: Text(s.status),
                      visualDensity: VisualDensity.compact,
                    ),
                    onTap: () async {
                      await Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => SettlementDetailScreen(
                              client: widget.client, settlementId: s.id),
                        ),
                      );
                      await _load();
                    },
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
                            _offset = (_offset - pageSize).clamp(0, 1 << 30);
                            _load();
                          },
                    child: const Text('Previous'),
                  ),
                  Text(
                      '${(_offset ~/ pageSize) + 1} / ${(page.total / pageSize).ceil()}'),
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
    );
  }
}

/// Detail: settlement fields, line list, totals, lifecycle actions.
class SettlementDetailScreen extends StatefulWidget {
  const SettlementDetailScreen(
      {super.key, required this.client, required this.settlementId});

  final ApiClient client;
  final String settlementId;

  @override
  State<SettlementDetailScreen> createState() => _SettlementDetailScreenState();
}

class _SettlementDetailScreenState extends State<SettlementDetailScreen> {
  SettlementDetailResult? _detail;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final detail = await widget.client.settlementDetail(widget.settlementId);
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

  Future<void> _action(String action) async {
    try {
      await widget.client.settlementAction(widget.settlementId, action);
      await _load();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.detail)));
    }
  }

  Future<void> _openFinalize() async {
    final settlement = _detail?.settlement;
    if (settlement == null) return;
    final confirmed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => FinalizeSettlementScreen(settlement: settlement),
      ),
    );
    if (confirmed == true) await _action('finalize');
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    final s = detail?.settlement;
    return Scaffold(
      appBar: AppBar(title: Text(s?.number ?? 'Settlement')),
      body: detail == null || s == null
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
                    title: Text('${s.periodFrom} → ${s.periodTo}'),
                    subtitle: Text('Gross ${s.grossAmount} ${s.currency} · '
                        'Net ${s.netAmount} ${s.currency}'),
                    trailing: Chip(
                      label: Text(s.status),
                      visualDensity: VisualDensity.compact,
                    ),
                  ),
                ),
                if (!detail.totalsMatch)
                  Card(
                    child: ListTile(
                      leading: Icon(Icons.warning_amber,
                          color: Theme.of(context).colorScheme.error),
                      title: const Text('Totals out of sync'),
                      subtitle: const Text('Recalculate before finalizing.'),
                    ),
                  ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    if (s.status == 'draft' || s.status == 'calculated')
                      FilledButton.tonal(
                        onPressed: () => _action('calculate'),
                        child: const Text('Calculate totals'),
                      ),
                    if (s.status == 'calculated')
                      FilledButton(
                        onPressed: _openFinalize,
                        child: const Text('Finalize'),
                      ),
                    if (s.status == 'draft' || s.status == 'calculated')
                      OutlinedButton(
                        onPressed: () => _action('cancel'),
                        child: const Text('Cancel settlement'),
                      ),
                  ],
                ),
                const SizedBox(height: 16),
                Text('Lines (${detail.lines.length})',
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 4),
                if (detail.lines.isEmpty)
                  const Text('No lines — add pricing calculations '
                      'from the portal or transaction flow.'),
                ...detail.lines.map(
                  (line) => Card(
                    child: ListTile(
                      dense: true,
                      title: Text(
                          '${line.quantity} ${line.quantityUnit} @ ${line.unitPrice}'),
                      subtitle: Text(line.transactionDate),
                      trailing: Text('${line.grossAmount} ${s.currency}'),
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}

/// Finalize confirmation: finalization is permanent (BR-0010).
class FinalizeSettlementScreen extends StatelessWidget {
  const FinalizeSettlementScreen({super.key, required this.settlement});

  final SettlementSummary settlement;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Finalize settlement')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(settlement.number,
                style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 8),
            Text('${settlement.periodFrom} → ${settlement.periodTo}'),
            Text('${settlement.lineCount} line(s)'),
            const SizedBox(height: 16),
            Text(
              'Net payable: ${settlement.netAmount} ${settlement.currency}',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 24),
            const Text('Finalizing is permanent: the settlement becomes '
                'immutable and its calculations stay locked to it.'),
            const Spacer(),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Finalize — this cannot be undone'),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Back'),
            ),
          ],
        ),
      ),
    );
  }
}
