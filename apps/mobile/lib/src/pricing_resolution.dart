import 'package:flutter/material.dart';

import 'api.dart';

/// Resolution Test Screen — PRC-003. Operators check which pricing matrix
/// band a transaction WOULD use. Selection only: no amounts are calculated.
class ResolutionTestScreen extends StatefulWidget {
  const ResolutionTestScreen(
      {super.key, required this.client, required this.centerId});

  final ApiClient client;
  final String centerId;

  @override
  State<ResolutionTestScreen> createState() => _ResolutionTestScreenState();
}

class _ResolutionTestScreenState extends State<ResolutionTestScreen> {
  final _formKey = GlobalKey<FormState>();
  final _product = TextEditingController();
  final _value = TextEditingController();
  List<DimensionSummary> _dimensions = const [];
  String? _dimensionCode;
  ResolutionResultView? _result;
  String? _failureMessage;
  String? _failureStage;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _loadDimensions();
  }

  Future<void> _loadDimensions() async {
    try {
      final dims = await widget.client.listQualityDimensions();
      if (mounted) {
        setState(() => _dimensions = dims.where((d) => d.active).toList());
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _failureMessage = e.detail);
    }
  }

  Future<void> _resolve() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _result = null;
      _failureMessage = null;
      _failureStage = null;
    });
    final today = DateTime.now();
    final date = '${today.year.toString().padLeft(4, '0')}-'
        '${today.month.toString().padLeft(2, '0')}-'
        '${today.day.toString().padLeft(2, '0')}';
    try {
      final result = await widget.client.resolvePricing(
        centerId: widget.centerId,
        productCode: _product.text.trim().toUpperCase(),
        transactionDate: date,
        dimensionCode: _dimensionCode!,
        value: double.parse(_value.text.trim()),
      );
      if (mounted) setState(() => _result = result);
    } on ApiException catch (e) {
      if (mounted) {
        setState(() {
          _failureMessage =
              (e.extra?['reason'] ?? e.detail).toString();
          _failureStage = e.extra?['stage']?.toString();
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final result = _result;
    return Scaffold(
      appBar: AppBar(title: const Text('Pricing resolution test')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  TextFormField(
                    controller: _product,
                    decoration:
                        const InputDecoration(labelText: 'Product code'),
                    textCapitalization: TextCapitalization.characters,
                    validator: (v) => (v == null || v.trim().length < 2)
                        ? 'Product code is required'
                        : null,
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: _dimensionCode,
                    decoration:
                        const InputDecoration(labelText: 'Quality dimension'),
                    items: _dimensions
                        .map((d) => DropdownMenuItem(
                              value: d.code,
                              child: Text('${d.code} — ${d.name}'),
                            ))
                        .toList(),
                    onChanged: (v) => setState(() => _dimensionCode = v),
                    validator: (v) => v == null ? 'Pick a dimension' : null,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _value,
                    decoration: const InputDecoration(
                        labelText: 'Reading value (e.g. 4.2)'),
                    keyboardType: TextInputType.number,
                    validator: (v) =>
                        (v == null || double.tryParse(v.trim()) == null)
                            ? 'Enter a numeric reading'
                            : null,
                  ),
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: _busy ? null : _resolve,
                    child: Text(_busy ? 'Resolving…' : 'Resolve'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            if (result != null)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Matched',
                          style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 8),
                      Text('Rate card: ${result.rateCardCode} '
                          'v${result.rateCardVersion}'),
                      Text('Matrix: ${result.matrixName}'),
                      Text('Band: [${result.rangeFrom} – ${result.rangeTo}) '
                          'for ${result.readingValue}${result.readingUnit}'),
                      const SizedBox(height: 8),
                      Text(
                        'Unit price: ${result.priceAmount} ${result.currency}',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Selection only — no amount is calculated.',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              ),
            if (_failureMessage != null)
              Card(
                child: ListTile(
                  leading: Icon(Icons.error_outline,
                      color: Theme.of(context).colorScheme.error),
                  title: Text(_failureStage != null
                      ? 'No resolution (failed at: $_failureStage)'
                      : 'No resolution'),
                  subtitle: Text(_failureMessage!),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
