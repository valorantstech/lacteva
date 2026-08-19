import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';

/// The centre's collection history (P1-MOBILE-COUNTER-001).
///
/// The phone's answer to a farmer's "you wrote 12.5 kg, not 15" — the audit
/// found the only mobile view of past collections was an aggregate, so a
/// dispute at the counter could not be answered where it happens. This screen
/// is READ-ONLY: the platform pages, filters by the centre asked for, and
/// authorizes every row (another tenant's or centre's data is simply not in
/// the answer). Tapping a completed row fetches its parchi — the platform's
/// own document, which carries the farmer's identity and the captured values.
class TransactionHistoryScreen extends StatefulWidget {
  const TransactionHistoryScreen({
    super.key,
    required this.client,
    required this.centerId,
    required this.centerName,
  });

  final ApiClient client;
  final String centerId;
  final String centerName;

  @override
  State<TransactionHistoryScreen> createState() =>
      _TransactionHistoryScreenState();
}

class _TransactionHistoryScreenState extends State<TransactionHistoryScreen> {
  static const pageSize = 20;
  final List<Map<String, dynamic>> _items = [];
  int _total = 0;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load(reset: true);
  }

  Future<void> _load({bool reset = false}) async {
    setState(() {
      _loading = true;
      if (reset) _error = null;
    });
    try {
      final page = await widget.client.listMilkTransactions(
        centerId: widget.centerId,
        limit: pageSize,
        offset: reset ? 0 : _items.length,
      );
      if (!mounted) return;
      setState(() {
        if (reset) _items.clear();
        _items.addAll(
          ((page['items'] as List?) ?? const []).cast<Map<String, dynamic>>(),
        );
        _total = (page['total'] as num?)?.toInt() ?? _items.length;
        _error = null;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (mounted) {
        setState(() {
          _error = e.detail;
          _loading = false;
        });
      }
    } catch (_) {
      // Transport failure ≠ refusal (P0-PRODUCT-008 D-1).
      if (mounted) {
        setState(() {
          _error = 'Could not reach the platform';
          _loading = false;
        });
      }
    }
  }

  Future<void> _openDetail(Map<String, dynamic> tx) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => TransactionDetailScreen(
          client: widget.client,
          transaction: tx,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Collections — ${widget.centerName}')),
      body: RefreshIndicator(
        onRefresh: () => _load(reset: true),
        child: ListView(
          padding: const EdgeInsets.all(12),
          children: [
            if (_error != null)
              Padding(
                padding: const EdgeInsets.all(8),
                child: Column(
                  children: [
                    Text(
                      _error!,
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                    TextButton(
                      onPressed: _loading ? null : () => _load(reset: true),
                      child: const Text('Try again'),
                    ),
                  ],
                ),
              ),
            if (_loading && _items.isEmpty && _error == null)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: CircularProgressIndicator()),
              ),
            if (!_loading && _items.isEmpty && _error == null)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(
                  child: Text('No collections recorded at this centre yet.'),
                ),
              ),
            for (final tx in _items)
              Card(
                child: ListTile(
                  leading: Icon(
                    tx['state'] == 'COMPLETED'
                        ? (tx['rejected_reason'] == null
                              ? Icons.check_circle_outline
                              : Icons.cancel_outlined)
                        : Icons.hourglass_bottom,
                  ),
                  title: Text(
                    tx['slip_number']?.toString() ??
                        '${tx['id']}'.substring(0, 8),
                  ),
                  subtitle: Text(
                    [
                      '${tx['created_at']}'.replaceFirst('T', ' ').split('.').first,
                      tx['milk_type']?.toString() ?? '—',
                      if (tx['net_weight'] != null) '${tx['net_weight']} kg',
                      tx['state'].toString(),
                    ].join(' · '),
                  ),
                  trailing: tx['gross_amount'] != null
                      ? Text('${tx['gross_amount']} ${tx['currency'] ?? ''}')
                      : null,
                  onTap: () => _openDetail(tx),
                ),
              ),
            if (_items.isNotEmpty && _items.length < _total)
              Padding(
                padding: const EdgeInsets.all(8),
                child: Center(
                  child: OutlinedButton(
                    onPressed: _loading ? null : () => _load(),
                    child: Text(
                      _loading
                          ? 'Loading…'
                          : 'Load more (${_items.length} of $_total)',
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// One past collection, with its parchi where the platform has one.
class TransactionDetailScreen extends StatefulWidget {
  const TransactionDetailScreen({
    super.key,
    required this.client,
    required this.transaction,
  });

  final ApiClient client;
  final Map<String, dynamic> transaction;

  @override
  State<TransactionDetailScreen> createState() =>
      _TransactionDetailScreenState();
}

class _TransactionDetailScreenState extends State<TransactionDetailScreen> {
  Map<String, dynamic>? _slip;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    if (widget.transaction['state'] == 'COMPLETED') _fetchSlip();
  }

  Future<void> _fetchSlip() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final slip = await widget.client.transactionSlip(
        widget.transaction['id'].toString(),
      );
      if (mounted) setState(() => _slip = slip);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.detail);
    } catch (_) {
      // Transport failure ≠ refusal (P0-PRODUCT-008 D-1).
      if (mounted) setState(() => _error = 'Could not reach the platform');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final tx = widget.transaction;
    final slip = _slip;
    return Scaffold(
      appBar: AppBar(
        title: Text(tx['slip_number']?.toString() ?? 'Collection'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('State: ${tx['state']}'),
                  Text('Milk: ${tx['milk_type'] ?? '—'}'),
                  Text('Net: ${tx['net_weight'] ?? '—'} kg'),
                  Text(
                    'FAT ${tx['fat_percentage'] ?? tx['fat'] ?? '—'} · '
                    'SNF ${tx['snf_percentage'] ?? tx['snf'] ?? '—'} · '
                    'CLR ${tx['clr_value'] ?? tx['clr'] ?? '—'}',
                  ),
                  if (tx['gross_amount'] != null)
                    Text('Amount: ${tx['gross_amount']} ${tx['currency']}'),
                  if (tx['rejected_reason'] != null)
                    Text('Rejected: ${tx['rejected_reason']}'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          if (_error != null)
            Column(
              children: [
                Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
                TextButton(
                  onPressed: _busy ? null : _fetchSlip,
                  child: const Text('Try again'),
                ),
              ],
            ),
          if (_busy)
            const Center(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: CircularProgressIndicator(),
              ),
            ),
          if (slip != null) ...[
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Parchi ${slip['slip_number']}',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '${slip['text']}',
                      style: const TextStyle(
                        fontFamily: 'monospace',
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            TextButton.icon(
              icon: const Icon(Icons.copy),
              label: const Text('Copy parchi text'),
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: '${slip['text']}'));
                if (!context.mounted) return;
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Parchi copied')),
                );
              },
            ),
          ],
        ],
      ),
    );
  }
}
