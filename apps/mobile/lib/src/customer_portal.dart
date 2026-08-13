/// The household's own app (DEMO-012 §6, §8).
///
/// What a customer wants to know, in the order they want to know it: did the
/// milk come today, what do I owe, and what is on this month's bill.
///
/// Every figure here is the platform's. The bill in particular is rendered
/// exactly as the backend computed it — line by line, with the backend's OWN
/// reconciliation verdict (`totals_match_lines`) shown rather than a sum this
/// app performed. Re-adding the lines in Dart would create a second billing
/// engine whose only possible contribution is to disagree with the first, in
/// front of the person being billed.
///
/// The scope is not enforced here. A customer login is narrowed to its own
/// customer by the PLATFORM (`core/tenancy.enforce_customer_scope`), so this
/// screen would be shown nothing else even if it asked. What it does here is
/// decide what to render, not what may be seen.
library;

import 'package:flutter/material.dart';

import 'api.dart';
import 'session.dart';

String _today() => DateTime.now().toUtc().toIso8601String().substring(0, 10);

String _monthStart() {
  final now = DateTime.now().toUtc();
  return '${now.year.toString().padLeft(4, '0')}-'
      '${now.month.toString().padLeft(2, '0')}-01';
}

class CustomerHomeScreen extends StatefulWidget {
  const CustomerHomeScreen({
    super.key,
    required this.client,
    required this.session,
  });

  final ApiClient client;
  final Session session;

  @override
  State<CustomerHomeScreen> createState() => _CustomerHomeScreenState();
}

class _CustomerHomeScreenState extends State<CustomerHomeScreen> {
  Map<String, dynamic>? _customer;
  Map<String, dynamic>? _balance;
  Map<String, dynamic>? _month;
  List<Map<String, dynamic>> _recent = const [];
  List<Map<String, dynamic>> _bills = const [];
  List<Map<String, dynamic>> _receipts = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final id = widget.session.customerId!;
      // Five aggregate calls for the whole screen. Not one per delivery, and
      // not one per bill (§13).
      final detail = await widget.client.customerDetail(id);
      final balance = await widget.client.customerBalance(id);
      final deliveries = await widget.client.listDeliveries(limit: 60);
      final bills = await widget.client.listInvoices(limit: 12);
      Map<String, dynamic>? month;
      try {
        month = await widget.client.deliveryReport(
          dateFrom: _monthStart(),
          dateTo: _today(),
        );
      } on ApiException {
        month = null;
      }
      List<Map<String, dynamic>> receipts = const [];
      try {
        final r = await widget.client.listCustomerReceipts(limit: 12);
        receipts = ((r['items'] as List?) ?? const [])
            .cast<Map<String, dynamic>>();
      } on ApiException {
        receipts = const [];
      }
      if (!mounted) return;
      setState(() {
        _customer = detail['customer'] as Map<String, dynamic>?;
        _balance = balance;
        _month = month;
        _recent = ((deliveries['items'] as List?) ?? const [])
            .cast<Map<String, dynamic>>();
        _bills = ((bills['items'] as List?) ?? const [])
            .cast<Map<String, dynamic>>();
        _receipts = receipts;
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
        _error =
            'Could not reach the dairy. Showing nothing rather than '
            'something out of date.';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final today = _today();
    final todays = _recent.where((d) => d['delivery_date'] == today).toList();
    return Scaffold(
      appBar: AppBar(
        title: Text(_customer?['name']?.toString() ?? 'My dairy'),
        actions: [
          IconButton(
            onPressed: _loading ? null : _load,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  if (_error != null)
                    Card(
                      color: Theme.of(context).colorScheme.errorContainer,
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Text(_error!),
                      ),
                    ),
                  _TodayCard(deliveries: todays),
                  const SizedBox(height: 12),
                  _BalanceCard(balance: _balance),
                  const SizedBox(height: 12),
                  if (_month != null) _MonthCard(report: _month!),
                  const SizedBox(height: 12),
                  _BillsCard(
                    bills: _bills,
                    onOpen: (bill) => Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => CustomerBillScreen(
                          client: widget.client,
                          invoiceId: bill['id'].toString(),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  _ReceiptsCard(receipts: _receipts),
                  const SizedBox(height: 12),
                  _HistoryCard(deliveries: _recent),
                ],
              ),
            ),
    );
  }
}

class _TodayCard extends StatelessWidget {
  const _TodayCard({required this.deliveries});

  final List<Map<String, dynamic>> deliveries;

  @override
  Widget build(BuildContext context) {
    final delivered = deliveries
        .where((d) => d['status'] == 'delivered')
        .toList(growable: false);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Today', style: Theme.of(context).textTheme.labelLarge),
            const SizedBox(height: 8),
            if (deliveries.isEmpty)
              const Text(
                'No delivery recorded yet today.',
                style: TextStyle(fontSize: 18),
              )
            else ...[
              for (final d in delivered)
                Text(
                  '${d['quantity']} ${d['quantity_unit'] ?? 'L'} — ${d['slot']}',
                  style: const TextStyle(
                    fontSize: 26,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              for (final d in deliveries.where(
                (d) => d['status'] != 'delivered',
              ))
                Text(
                  '${d['slot']}: ${d['status']}',
                  style: const TextStyle(fontSize: 18),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _BalanceCard extends StatelessWidget {
  const _BalanceCard({required this.balance});

  final Map<String, dynamic>? balance;

  @override
  Widget build(BuildContext context) {
    final b = balance;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('What I owe', style: Theme.of(context).textTheme.labelLarge),
            const SizedBox(height: 8),
            Text(
              '${b?['outstanding'] ?? '—'} ${b?['currency'] ?? ''}',
              style: const TextStyle(fontSize: 30, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text('Billed ${b?['invoiced'] ?? '—'} · paid ${b?['paid'] ?? '—'}'),
            if ((b?['unbilled_deliveries'] ?? 0) != 0)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(
                  '${b?['unbilled_deliveries']} delivery(s) not yet on a bill '
                  '(${b?['unbilled_amount']})',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Consumption this month, aggregated by the database (§6).
class _MonthCard extends StatelessWidget {
  const _MonthCard({required this.report});

  final Map<String, dynamic> report;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('This month', style: Theme.of(context).textTheme.labelLarge),
            const SizedBox(height: 8),
            Text(
              '${report['total_quantity'] ?? 0} ${report['quantity_unit'] ?? 'L'}',
              style: const TextStyle(fontSize: 26, fontWeight: FontWeight.bold),
            ),
            Text(
              '${report['deliveries'] ?? 0} deliveries · '
              '${report['total_amount'] ?? '—'}',
            ),
          ],
        ),
      ),
    );
  }
}

class _BillsCard extends StatelessWidget {
  const _BillsCard({required this.bills, required this.onOpen});

  final List<Map<String, dynamic>> bills;
  final void Function(Map<String, dynamic>) onOpen;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
            child: Text(
              'My bills',
              style: Theme.of(context).textTheme.labelLarge,
            ),
          ),
          if (bills.isEmpty)
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 0, 20, 20),
              child: Text('No bill has been issued yet.'),
            )
          else
            for (final bill in bills)
              ListTile(
                title: Text(bill['invoice_number']?.toString() ?? '—'),
                subtitle: Text(
                  '${bill['period_from']} → ${bill['period_to']} · ${bill['status']}',
                ),
                trailing: Text(
                  '${bill['amount_due']} ${bill['currency'] ?? ''}',
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                onTap: () => onOpen(bill),
              ),
        ],
      ),
    );
  }
}

class _ReceiptsCard extends StatelessWidget {
  const _ReceiptsCard({required this.receipts});

  final List<Map<String, dynamic>> receipts;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
            child: Text(
              'My receipts',
              style: Theme.of(context).textTheme.labelLarge,
            ),
          ),
          if (receipts.isEmpty)
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 0, 20, 20),
              child: Text('A receipt appears here after each payment.'),
            )
          else
            for (final r in receipts)
              ListTile(
                dense: true,
                title: Text(r['receipt_number']?.toString() ?? '—'),
                subtitle: Text(r['payment_number']?.toString() ?? ''),
                trailing: Text('${r['amount']} ${r['currency'] ?? ''}'),
              ),
        ],
      ),
    );
  }
}

class _HistoryCard extends StatelessWidget {
  const _HistoryCard({required this.deliveries});

  final List<Map<String, dynamic>> deliveries;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
            child: Text(
              'Delivery history',
              style: Theme.of(context).textTheme.labelLarge,
            ),
          ),
          if (deliveries.isEmpty)
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 0, 20, 20),
              child: Text('No deliveries recorded yet.'),
            )
          else
            for (final d in deliveries.take(30))
              ListTile(
                dense: true,
                leading: Icon(
                  d['status'] == 'delivered'
                      ? Icons.check_circle_outline
                      : Icons.remove_circle_outline,
                  color: d['status'] == 'delivered' ? Colors.green : null,
                ),
                title: Text('${d['delivery_date']} · ${d['slot']}'),
                subtitle: Text(d['status']?.toString() ?? ''),
                trailing: Text(
                  d['status'] == 'delivered'
                      ? '${d['quantity']} ${d['quantity_unit'] ?? 'L'}'
                      : '—',
                ),
              ),
        ],
      ),
    );
  }
}

/// One monthly bill, exactly as the platform computed it (§8).
class CustomerBillScreen extends StatefulWidget {
  const CustomerBillScreen({
    super.key,
    required this.client,
    required this.invoiceId,
  });

  final ApiClient client;
  final String invoiceId;

  @override
  State<CustomerBillScreen> createState() => _CustomerBillScreenState();
}

class _CustomerBillScreenState extends State<CustomerBillScreen> {
  Map<String, dynamic>? _detail;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d = await widget.client.invoiceDetail(widget.invoiceId);
      if (!mounted) return;
      setState(() => _detail = d);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.detail);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = _detail;
    final invoice = d?['invoice'] as Map<String, dynamic>?;
    final lines = ((d?['lines'] as List?) ?? const [])
        .cast<Map<String, dynamic>>();
    return Scaffold(
      appBar: AppBar(
        title: Text(invoice?['invoice_number']?.toString() ?? 'Bill'),
      ),
      body: _error != null
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(_error!),
              ),
            )
          : d == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${invoice?['period_from']} → ${invoice?['period_to']}',
                          style: Theme.of(context).textTheme.labelLarge,
                        ),
                        const SizedBox(height: 12),
                        _Row('Deliveries', '${invoice?['line_count'] ?? 0}'),
                        _Row('Subtotal', '${invoice?['subtotal']}'),
                        _Row('Adjustments', '${invoice?['adjustments']}'),
                        _Row(
                          'Brought forward',
                          '${invoice?['previous_balance']}',
                        ),
                        const Divider(),
                        _Row(
                          'Amount due',
                          '${invoice?['amount_due']} ${invoice?['currency'] ?? ''}',
                          bold: true,
                        ),
                        _Row('Paid', '${d['paid']}'),
                        _Row('Outstanding', '${d['outstanding']}', bold: true),
                        const SizedBox(height: 12),
                        // The PLATFORM's verdict, not a sum performed here.
                        Row(
                          children: [
                            Icon(
                              d['totals_match_lines'] == true
                                  ? Icons.verified_outlined
                                  : Icons.warning_amber_outlined,
                              size: 18,
                              color: d['totals_match_lines'] == true
                                  ? Colors.green
                                  : Theme.of(context).colorScheme.error,
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                d['totals_match_lines'] == true
                                    ? 'Checked by the dairy: this bill matches '
                                          'the deliveries below.'
                                    : 'This bill no longer matches its '
                                          'deliveries. Contact the dairy.',
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Card(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: const EdgeInsets.fromLTRB(20, 20, 20, 4),
                        child: Text(
                          'Every delivery on this bill',
                          style: Theme.of(context).textTheme.labelLarge,
                        ),
                      ),
                      for (final line in lines)
                        ListTile(
                          dense: true,
                          title: Text(
                            '${line['delivery_date']} · ${line['slot']}',
                          ),
                          subtitle: Text(
                            '${line['quantity']} ${line['quantity_unit'] ?? 'L'} '
                            '@ ${line['unit_price']}',
                          ),
                          trailing: Text(line['amount']?.toString() ?? ''),
                        ),
                    ],
                  ),
                ),
              ],
            ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row(this.label, this.value, {this.bold = false});

  final String label;
  final String value;
  final bool bold;

  @override
  Widget build(BuildContext context) {
    final style = TextStyle(
      fontWeight: bold ? FontWeight.bold : FontWeight.normal,
      fontSize: bold ? 17 : 15,
    );
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: style),
          Text(value, style: style),
        ],
      ),
    );
  }
}
