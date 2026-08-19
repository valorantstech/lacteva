import 'package:flutter/material.dart';

import 'api.dart';

/// Payment history — PAY-001.
///
/// Read-only by design: a field device shows what was paid so an operator can
/// answer "has this farmer been paid yet?". Executing a payment is a
/// back-office act and stays in the portal.
class PaymentHistoryScreen extends StatefulWidget {
  const PaymentHistoryScreen({super.key, required this.client});

  final ApiClient client;

  @override
  State<PaymentHistoryScreen> createState() => _PaymentHistoryScreenState();
}

class _PaymentHistoryScreenState extends State<PaymentHistoryScreen> {
  static const pageSize = 20;
  static const statuses = ['', 'completed', 'processing', 'failed', 'draft'];

  final _search = TextEditingController();
  PaymentPageResult? _page;
  String _status = '';
  int _offset = 0;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final page = await widget.client.listPayments(
        query: _search.text.trim(),
        status: _status,
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
      if (mounted) setState(() => _error = 'Could not reach the platform');
    }
  }

  @override
  Widget build(BuildContext context) {
    final page = _page;
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Payments')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextField(
              controller: _search,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Search payment number or reference',
              ),
              onSubmitted: (_) {
                _offset = 0;
                _load();
              },
            ),
            const SizedBox(height: 12),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: statuses
                    .map(
                      (s) => Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: ChoiceChip(
                          label: Text(s.isEmpty ? 'All' : s),
                          selected: _status == s,
                          onSelected: (_) {
                            setState(() {
                              _status = s;
                              _offset = 0;
                            });
                            _load();
                          },
                        ),
                      ),
                    )
                    .toList(),
              ),
            ),
            const SizedBox(height: 12),
            if (_error != null)
              Text(_error!, style: TextStyle(color: scheme.error)),
            if (page == null && _error == null)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: CircularProgressIndicator()),
              ),
            if (page != null && page.items.isEmpty)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: Text('No payments yet.')),
              ),
            if (page != null)
              ...page.items.map(
                (p) => Card(
                  child: ListTile(
                    leading: Icon(
                      paymentIcon(p.status),
                      color: paymentColor(p.status, scheme),
                    ),
                    title: Text('${p.amount} ${p.currency}'),
                    subtitle: Text(
                      '${p.number} · ${p.method.replaceAll('_', ' ').toLowerCase()}\n'
                      '${p.lineCount} settlement(s) · '
                      '${p.createdAt.replaceFirst('T', ' ').split('.').first}',
                    ),
                    isThreeLine: true,
                    trailing: Chip(
                      label: Text(p.status),
                      visualDensity: VisualDensity.compact,
                    ),
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => PaymentDetailScreen(
                          client: widget.client,
                          paymentId: p.id,
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
                            _offset = (_offset - pageSize).clamp(0, 1 << 30);
                            _load();
                          },
                    child: const Text('Previous'),
                  ),
                  Text(
                    '${(_offset ~/ pageSize) + 1} / '
                    '${(page.total / pageSize).ceil()}',
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
    );
  }
}

IconData paymentIcon(String status) => switch (status) {
  'completed' => Icons.check_circle_outline,
  'failed' => Icons.error_outline,
  'cancelled' => Icons.block,
  'processing' => Icons.hourglass_top,
  _ => Icons.payments_outlined,
};

Color paymentColor(String status, ColorScheme scheme) => switch (status) {
  'completed' => Colors.green,
  'failed' => scheme.error,
  'cancelled' => scheme.outline,
  'processing' => Colors.orange,
  _ => scheme.primary,
};

/// What was paid, against which settlements, and every attempt it took.
class PaymentDetailScreen extends StatefulWidget {
  const PaymentDetailScreen({
    super.key,
    required this.client,
    required this.paymentId,
  });

  final ApiClient client;
  final String paymentId;

  @override
  State<PaymentDetailScreen> createState() => _PaymentDetailScreenState();
}

class _PaymentDetailScreenState extends State<PaymentDetailScreen> {
  PaymentDetailResult? _detail;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final detail = await widget.client.paymentDetail(widget.paymentId);
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
      if (mounted) setState(() => _error = 'Could not reach the platform');
    }
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    final p = detail?.payment;
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: Text(p?.number ?? 'Payment')),
      body: detail == null || p == null
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
                    leading: Icon(
                      paymentIcon(p.status),
                      color: paymentColor(p.status, scheme),
                    ),
                    title: Text('${p.amount} ${p.currency}'),
                    subtitle: Text(
                      '${p.method.replaceAll('_', ' ').toLowerCase()}'
                      '${p.reference != null ? ' · ref ${p.reference}' : ''}',
                    ),
                    trailing: Chip(
                      label: Text(p.status),
                      visualDensity: VisualDensity.compact,
                    ),
                  ),
                ),
                if (p.failureReason != null)
                  Card(
                    child: ListTile(
                      leading: Icon(Icons.warning_amber, color: scheme.error),
                      title: const Text('Last failure'),
                      subtitle: Text(p.failureReason!),
                    ),
                  ),
                const SizedBox(height: 8),
                Text(
                  'Settlements paid (${detail.lines.length})',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                ...detail.lines.map(
                  (line) => Card(
                    child: ListTile(
                      dense: true,
                      title: Text(line.settlementNumber),
                      trailing: Text('${line.amount} ${p.currency}'),
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Attempts (${detail.attempts.length})',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                if (detail.attempts.isEmpty)
                  const ListTile(dense: true, title: Text('Not executed yet.')),
                ...detail.attempts.map(
                  (a) => Card(
                    child: ListTile(
                      dense: true,
                      leading: Text('#${a.attemptNumber}'),
                      title: Text('${a.provider} · ${a.status}'),
                      subtitle: Text(
                        a.failureReason ??
                            a.startedAt.replaceFirst('T', ' ').split('.').first,
                      ),
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}
