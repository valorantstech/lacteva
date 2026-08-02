import 'package:flutter/material.dart';

import 'api.dart';

/// Milk Collection Transaction Wizard (SPRINT-007).
/// Steps: supplier -> milk -> weight -> quality -> review -> completion.
class CollectionWizardScreen extends StatefulWidget {
  const CollectionWizardScreen({
    super.key,
    required this.client,
    required this.sessionId,
  });

  final ApiClient client;
  final String sessionId;

  @override
  State<CollectionWizardScreen> createState() => _CollectionWizardScreenState();
}

class _CollectionWizardScreenState extends State<CollectionWizardScreen> {
  int _step = 0;
  String? _txId;
  Map<String, dynamic>? _tx;
  String? _error;
  bool _busy = false;

  // Supplier step
  final _supplierCode = TextEditingController();
  // Milk step
  String _milkType = 'cow';
  final _containerType = TextEditingController(text: 'can');
  final _containerId = TextEditingController();
  // Weight step
  final _gross = TextEditingController();
  final _tare = TextEditingController();
  // Quality step
  final _fat = TextEditingController();
  final _snf = TextEditingController();
  final _clr = TextEditingController();

  Future<void> _run(Future<Map<String, dynamic>> Function() action,
      {int? nextStep}) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final tx = await action();
      setState(() {
        _tx = tx;
        _txId = tx['id'] as String? ?? _txId;
        if (nextStep != null) _step = nextStep;
      });
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } catch (_) {
      setState(() => _error = 'Could not reach the platform');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _identify() async {
    await _run(() async {
      final tx = await widget.client
          .txStep('/v1/milk-transactions', body: {'session_id': widget.sessionId});
      return widget.client.txStep(
        '/v1/milk-transactions/${tx['id']}/identify',
        body: {'method': 'code', 'value': _supplierCode.text.trim()},
      );
    }, nextStep: 1);
  }

  Future<void> _milk() => _run(
        () => widget.client.txStep('/v1/milk-transactions/$_txId/milk', body: {
          'milk_type': _milkType,
          'container_type': _containerType.text.trim(),
          'container_identifier': _containerId.text.trim(),
        }),
        nextStep: 2,
      );

  Future<void> _weight({required bool mock}) => _run(
        () => widget.client.txStep('/v1/milk-transactions/$_txId/weight', body: {
          'source': mock ? 'mock_scale' : 'manual',
          if (!mock) 'gross': double.tryParse(_gross.text),
          if (!mock) 'tare': double.tryParse(_tare.text),
        }),
        nextStep: 3,
      );

  Future<void> _quality({required bool mock}) => _run(
        () => widget.client.txStep('/v1/milk-transactions/$_txId/quality', body: {
          'source': mock ? 'mock_analyzer' : 'manual',
          if (!mock) 'fat': double.tryParse(_fat.text),
          if (!mock) 'snf': double.tryParse(_snf.text),
          if (!mock) 'clr': double.tryParse(_clr.text),
        }),
        nextStep: 4,
      );

  Future<void> _decide(bool accept) async {
    await _run(() async {
      if (accept) {
        await widget.client.txStep('/v1/milk-transactions/$_txId/accept');
      } else {
        await widget.client.txStep('/v1/milk-transactions/$_txId/reject',
            body: {'reason': 'Rejected at review'});
      }
      return widget.client.txStep('/v1/milk-transactions/$_txId/complete');
    }, nextStep: 5);
  }

  @override
  Widget build(BuildContext context) {
    final tx = _tx;
    return Scaffold(
      appBar: AppBar(title: Text('Collection — step ${_step + 1} of 6')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(_error!,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error)),
              ),
            if (_step == 0) ...[
              Text('Supplier', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 12),
              TextField(
                controller: _supplierCode,
                decoration: const InputDecoration(
                  labelText: 'Supplier code',
                  helperText: 'QR scanning arrives with device integration',
                ),
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : _identify,
                child: const Text('Identify supplier'),
              ),
            ],
            if (_step == 1) ...[
              Text('Milk', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _milkType,
                decoration: const InputDecoration(labelText: 'Milk type'),
                items: const ['cow', 'buffalo', 'goat', 'mixed']
                    .map((t) => DropdownMenuItem(value: t, child: Text(t)))
                    .toList(),
                onChanged: (v) => setState(() => _milkType = v ?? 'cow'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _containerType,
                decoration: const InputDecoration(labelText: 'Container type'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _containerId,
                decoration:
                    const InputDecoration(labelText: 'Container identifier'),
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : _milk,
                child: const Text('Receive milk'),
              ),
            ],
            if (_step == 2) ...[
              Text('Weight', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 12),
              TextField(
                controller: _gross,
                decoration: const InputDecoration(labelText: 'Gross (kg)'),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _tare,
                decoration: const InputDecoration(labelText: 'Tare (kg)'),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : () => _weight(mock: false),
                child: const Text('Capture weight'),
              ),
              TextButton(
                onPressed: _busy ? null : () => _weight(mock: true),
                child: const Text('Use mock scale'),
              ),
            ],
            if (_step == 3) ...[
              Text('Quality', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 12),
              TextField(
                controller: _fat,
                decoration: const InputDecoration(labelText: 'FAT %'),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _snf,
                decoration: const InputDecoration(labelText: 'SNF %'),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _clr,
                decoration: const InputDecoration(labelText: 'CLR'),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : () => _quality(mock: false),
                child: const Text('Capture quality'),
              ),
              TextButton(
                onPressed: _busy ? null : () => _quality(mock: true),
                child: const Text('Use mock analyzer'),
              ),
            ],
            if (_step == 4 && tx != null) ...[
              Text('Review', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 12),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Net weight: ${tx['net_weight']} kg'),
                      Text('FAT ${tx['fat']} · SNF ${tx['snf']} · CLR ${tx['clr']}'),
                      Text('Pricing: ${tx['pricing_status']}'),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : () => _decide(true),
                child: const Text('Accept & complete'),
              ),
              OutlinedButton(
                onPressed: _busy ? null : () => _decide(false),
                child: const Text('Reject & complete'),
              ),
            ],
            if (_step == 5 && tx != null) ...[
              const SizedBox(height: 24),
              Icon(
                tx['rejected_reason'] == null
                    ? Icons.check_circle
                    : Icons.cancel,
                size: 72,
                color:
                    tx['rejected_reason'] == null ? Colors.green : Colors.red,
              ),
              const SizedBox(height: 12),
              Center(
                child: Text('Transaction ${tx['state']}',
                    style: Theme.of(context).textTheme.titleLarge),
              ),
              Center(child: Text('Net ${tx['net_weight']} kg')),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('Done'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
