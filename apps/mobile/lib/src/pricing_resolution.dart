import 'package:flutter/material.dart';

import 'api.dart';
import 'format.dart';
import 'session.dart';

/// Resolution + Calculator Test Screen (PRC-003/PRC-004). Operators check
/// which pricing band a transaction WOULD use, then calculate the gross
/// amount for a quantity — with the full calculation trace.
class ResolutionTestScreen extends StatefulWidget {
  const ResolutionTestScreen({
    super.key,
    required this.client,
    required this.centerId,
    this.session,
  });

  final ApiClient client;
  final String centerId;

  /// Threaded for parity with the other centre screens
  /// (P1-LOCALE-I18N-001); this screen's strings are deliberately NOT
  /// localized yet — deferred with the back-office wave.
  final Session? session;

  @override
  State<ResolutionTestScreen> createState() => _ResolutionTestScreenState();
}

class _ResolutionTestScreenState extends State<ResolutionTestScreen> {
  final _formKey = GlobalKey<FormState>();
  final _product = TextEditingController();
  final _value = TextEditingController();
  final _quantity = TextEditingController();
  List<DimensionSummary> _dimensions = const [];
  String? _dimensionCode;
  ResolutionResultView? _result;
  CalculationResultView? _calculation;
  String? _failureMessage;
  String? _failureStage;
  bool _busy = false;

  String get _today {
    final now = DateTime.now();
    return '${now.year.toString().padLeft(4, '0')}-'
        '${now.month.toString().padLeft(2, '0')}-'
        '${now.day.toString().padLeft(2, '0')}';
  }

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
    } catch (_) {
      // Transport failure ≠ refusal (P0-PRODUCT-008 D-1).
      if (mounted) setState(() => _failureMessage = 'Could not reach the platform');
    }
  }

  Future<void> _resolve() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _result = null;
      _calculation = null;
      _failureMessage = null;
      _failureStage = null;
    });
    try {
      final result = await widget.client.resolvePricing(
        centerId: widget.centerId,
        productCode: _product.text.trim().toUpperCase(),
        transactionDate: _today,
        dimensionCode: _dimensionCode!,
        value: double.parse(_value.text.trim()),
      );
      if (mounted) setState(() => _result = result);
    } on ApiException catch (e) {
      if (mounted) {
        setState(() {
          _failureMessage = (e.extra?['reason'] ?? e.detail).toString();
          _failureStage = e.extra?['stage']?.toString();
        });
      }
    } catch (_) {
      // Transport failure ≠ refusal (P0-PRODUCT-008 D-1).
      if (mounted) setState(() => _failureMessage = 'Could not reach the platform');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _calculate() async {
    final result = _result;
    final quantity = double.tryParse(_quantity.text.trim());
    if (result == null || quantity == null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Enter a numeric quantity')));
      return;
    }
    try {
      final calculation = await widget.client.calculatePricing(
        rowId: result.rowId,
        quantity: quantity,
        transactionDate: _today,
      );
      if (mounted) setState(() => _calculation = calculation);
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text((e.extra?['reason'] ?? e.detail).toString())),
      );
    } catch (_) {
      // Transport failure ≠ refusal (P0-PRODUCT-008 D-1).
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Could not reach the platform')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final result = _result;
    final calculation = _calculation;
    return Scaffold(
      appBar: AppBar(title: const Text('Pricing test')),
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
                    decoration: const InputDecoration(
                      labelText: 'Product code',
                    ),
                    textCapitalization: TextCapitalization.characters,
                    validator: (v) => (v == null || v.trim().length < 2)
                        ? 'Product code is required'
                        : null,
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: _dimensionCode,
                    decoration: const InputDecoration(
                      labelText: 'Quality dimension',
                    ),
                    items: _dimensions
                        .map(
                          (d) => DropdownMenuItem(
                            value: d.code,
                            child: Text('${d.code} — ${d.name}'),
                          ),
                        )
                        .toList(),
                    onChanged: (v) => setState(() => _dimensionCode = v),
                    validator: (v) => v == null ? 'Pick a dimension' : null,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _value,
                    decoration: const InputDecoration(
                      labelText: 'Reading value (e.g. 4.2)',
                    ),
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
                      Text(
                        'Matched',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Rate card: ${result.rateCardCode} '
                        'v${result.rateCardVersion}',
                      ),
                      Text('Matrix: ${result.matrixName}'),
                      Text(
                        'Band: [${result.rangeFrom} – ${result.rangeTo}) '
                        'for ${result.readingValue}${result.readingUnit}',
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Unit price: ${result.priceAmount} ${result.currency}',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const Divider(height: 24),
                      Text(
                        'Calculate gross amount',
                        style: Theme.of(context).textTheme.titleSmall,
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _quantity,
                              decoration: InputDecoration(
                                labelText: 'Quantity (${orgUnit(widget.session)})',
                              ),
                              keyboardType: TextInputType.number,
                            ),
                          ),
                          const SizedBox(width: 8),
                          FilledButton.tonal(
                            onPressed: _calculate,
                            child: const Text('Calculate'),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            if (calculation != null)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Gross: ${calculation.grossAmount} '
                        '${calculation.currency}',
                        style: Theme.of(context).textTheme.headlineSmall,
                      ),
                      Text(
                        '${calculation.unitPrice} ${calculation.currency}'
                        ' x ${calculation.quantityValue}'
                        ' ${calculation.quantityUnit}'
                        ' · ${calculation.roundingPolicy}'
                        ' · calculator v${calculation.calculatorVersion}',
                      ),
                      const SizedBox(height: 12),
                      Text(
                        'Trace',
                        style: Theme.of(context).textTheme.titleSmall,
                      ),
                      ...calculation.trace.map(
                        (step) => Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text('${step.operation}: ${step.detail}'),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'No bonuses, penalties, or taxes — PRC-005+.',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              ),
            if (_failureMessage != null)
              Card(
                child: ListTile(
                  leading: Icon(
                    Icons.error_outline,
                    color: Theme.of(context).colorScheme.error,
                  ),
                  title: Text(
                    _failureStage != null
                        ? 'No resolution (failed at: $_failureStage)'
                        : 'No resolution',
                  ),
                  subtitle: Text(_failureMessage!),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
