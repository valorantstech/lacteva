import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'build_flags.dart';

/// The platform's own capture bounds, mirrored for the OFFLINE path
/// (P1-MOBILE-COUNTER-001; audit D-8). Online, the server refuses garbage
/// immediately; offline, this check is the only thing standing between a
/// mistyped 1200 kg and a conflict surfacing hours later at sync — when the
/// farmer is gone. Values are copied from `milk_collection/service.py`
/// (MAX_GROSS_KG, QUALITY_RANGES), never invented here; the backend stays
/// authoritative and re-checks everything on sync.
const kMaxGrossKg = 200.0;
const kFatRange = (0.0, 15.0);
const kSnfRange = (0.0, 15.0);
const kClrRange = (20.0, 40.0);

/// Milk Collection Transaction Wizard (SPRINT-007).
/// Steps: supplier -> milk -> weight -> quality -> review -> completion.
class CollectionWizardScreen extends StatefulWidget {
  const CollectionWizardScreen({
    super.key,
    required this.client,
    required this.sessionId,
    this.initialStep = 0,
  });

  final ApiClient client;
  final String sessionId;

  /// Which step to open on. Exists so a widget test can assert what a given
  /// step offers without driving five API round trips to reach it; the app
  /// always starts at 0.
  final int initialStep;

  @override
  State<CollectionWizardScreen> createState() => _CollectionWizardScreenState();
}

class _CollectionWizardScreenState extends State<CollectionWizardScreen> {
  late int _step = widget.initialStep;
  String? _txId;
  Map<String, dynamic>? _tx;
  String? _error;
  bool _busy = false;

  // The parchi (P1-MOBILE-COUNTER-001): fetched from the platform once the
  // transaction is COMPLETED online. An offline completion has no slip yet —
  // the number is minted by the platform, never invented on the phone.
  Map<String, dynamic>? _slip;
  bool _slipBusy = false;

  // Rejection asks WHY (audit D-7): the reason prints on the farmer's
  // official parchi, so a hardcoded placeholder was never acceptable.
  bool _rejecting = false;
  final _rejectReason = TextEditingController();

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

  Future<void> _run(
    Future<Map<String, dynamic>> Function() action, {
    int? nextStep,
  }) async {
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
      final tx = await widget.client.txStep(
        '/v1/milk-transactions',
        body: {'session_id': widget.sessionId},
      );
      return widget.client.txStep(
        '/v1/milk-transactions/${tx['id']}/identify',
        body: {'method': 'code', 'value': _supplierCode.text.trim()},
      );
    }, nextStep: 1);
  }

  Future<void> _milk() => _run(
    () => widget.client.txStep(
      '/v1/milk-transactions/$_txId/milk',
      body: {
        'milk_type': _milkType,
        'container_type': _containerType.text.trim(),
        'container_identifier': _containerId.text.trim(),
      },
    ),
    nextStep: 2,
  );

  /// The platform's weight rules, checked BEFORE anything can queue. Wording
  /// mirrors the server's own refusals so online and offline read the same.
  String? _weightProblem() {
    final gross = double.tryParse(_gross.text.trim());
    final tare = double.tryParse(_tare.text.trim());
    if (gross == null || tare == null) {
      return 'Enter gross and tare as numbers';
    }
    if (gross <= 0 || tare < 0) return 'gross must be > 0 and tare >= 0';
    if (gross > kMaxGrossKg) return 'gross weight exceeds $kMaxGrossKg kg limit';
    if (tare >= gross) return 'tare must be less than gross';
    return null;
  }

  /// The platform's quality plausibility bounds (QUALITY_RANGES), likewise.
  String? _qualityProblem() {
    final values = {
      'fat': (double.tryParse(_fat.text.trim()), kFatRange),
      'snf': (double.tryParse(_snf.text.trim()), kSnfRange),
      'clr': (double.tryParse(_clr.text.trim()), kClrRange),
    };
    for (final entry in values.entries) {
      final (value, (lo, hi)) = entry.value;
      if (value == null) return 'Enter fat, snf and clr as numbers';
      if (value < lo || value > hi) {
        return '${entry.key} out of range [$lo, $hi]';
      }
    }
    return null;
  }

  Future<void> _weight({required bool mock}) async {
    if (!mock) {
      final problem = _weightProblem();
      if (problem != null) {
        setState(() => _error = problem);
        return;
      }
    }
    await _run(
      () => widget.client.txStep(
        '/v1/milk-transactions/$_txId/weight',
        body: {
          'source': mock ? 'mock_scale' : 'manual',
          if (!mock) 'gross': double.tryParse(_gross.text),
          if (!mock) 'tare': double.tryParse(_tare.text),
        },
      ),
      nextStep: 3,
    );
  }

  Future<void> _quality({required bool mock}) async {
    if (!mock) {
      final problem = _qualityProblem();
      if (problem != null) {
        setState(() => _error = problem);
        return;
      }
    }
    await _run(
      () => widget.client.txStep(
        '/v1/milk-transactions/$_txId/quality',
        body: {
          'source': mock ? 'mock_analyzer' : 'manual',
          if (!mock) 'fat': double.tryParse(_fat.text),
          if (!mock) 'snf': double.tryParse(_snf.text),
          if (!mock) 'clr': double.tryParse(_clr.text),
        },
      ),
      nextStep: 4,
    );
  }

  Future<void> _decide(bool accept) async {
    if (!accept && _rejectReason.text.trim().isEmpty) {
      setState(() {
        _rejecting = true;
        _error = 'Say why the milk is rejected — it prints on the parchi';
      });
      return;
    }
    await _run(() async {
      if (accept) {
        await widget.client.txStep('/v1/milk-transactions/$_txId/accept');
      } else {
        await widget.client.txStep(
          '/v1/milk-transactions/$_txId/reject',
          body: {'reason': _rejectReason.text.trim()},
        );
      }
      return widget.client.txStep('/v1/milk-transactions/$_txId/complete');
    }, nextStep: 5);
    // COMPLETED online → the platform has minted the slip; fetch the parchi.
    // Queued offline → there is no slip yet, and the screen says so honestly.
    if (_step == 5 && _tx?['offline'] != true) {
      await _fetchSlip();
    }
  }

  Future<void> _fetchSlip() async {
    final id = _txId;
    if (id == null) return;
    setState(() => _slipBusy = true);
    try {
      final slip = await widget.client.transactionSlip(id);
      if (mounted) setState(() => _slip = slip);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.detail);
    } catch (_) {
      // Transport failure ≠ refusal (P0-PRODUCT-008 D-1): the completion
      // stands; the parchi has its own retry button below.
      if (mounted) setState(() => _error = 'Could not reach the platform');
    } finally {
      if (mounted) setState(() => _slipBusy = false);
    }
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
                child: Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
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
                decoration: const InputDecoration(
                  labelText: 'Container identifier',
                ),
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
              // SEC-003 / F-01: absent from a release build, not hidden.
              if (kMockHardwareEnabled)
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
              if (kMockHardwareEnabled)
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
                      Text(
                        'FAT ${tx['fat']} · SNF ${tx['snf']} · CLR ${tx['clr']}',
                      ),
                      const Divider(),
                      if (tx['pricing_status'] == 'priced') ...[
                        Text(
                          '${tx['gross_amount']} ${tx['currency']}',
                          style: Theme.of(context).textTheme.headlineSmall,
                        ),
                        Text(
                          '${tx['unit_price']} ${tx['currency']}/kg · '
                          '${tx['pricing_detail']}',
                        ),
                      ] else ...[
                        Text('Pricing: ${tx['pricing_status']}'),
                        if (tx['pricing_detail'] != null)
                          Text(
                            '${tx['pricing_detail']}',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                      ],
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : () => _decide(true),
                child: const Text('Accept & complete'),
              ),
              if (!_rejecting)
                OutlinedButton(
                  onPressed: _busy
                      ? null
                      : () => setState(() => _rejecting = true),
                  child: const Text('Reject…'),
                ),
              if (_rejecting) ...[
                const SizedBox(height: 12),
                TextField(
                  controller: _rejectReason,
                  decoration: const InputDecoration(
                    labelText: 'Rejection reason',
                    helperText:
                        'The farmer reads this on the parchi — say what was '
                        'actually wrong (sour, adulterated, smell…)',
                  ),
                ),
                const SizedBox(height: 8),
                OutlinedButton(
                  onPressed: _busy ? null : () => _decide(false),
                  child: const Text('Reject & complete'),
                ),
                TextButton(
                  onPressed: _busy
                      ? null
                      : () => setState(() {
                          _rejecting = false;
                          _rejectReason.clear();
                        }),
                  child: const Text('Keep reviewing'),
                ),
              ],
            ],
            if (_step == 5 && tx != null) ...[
              const SizedBox(height: 24),
              Icon(
                tx['rejected_reason'] == null
                    ? Icons.check_circle
                    : Icons.cancel,
                size: 72,
                color: tx['rejected_reason'] == null
                    ? Colors.green
                    : Colors.red,
              ),
              const SizedBox(height: 12),
              Center(
                child: Text(
                  // The honest status line: an offline completion is SAVED
                  // AND QUEUED, not submitted — the two must never blur.
                  tx['offline'] == true
                      ? 'Saved on this phone — queued to sync'
                      : 'Transaction ${tx['state']}',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              Center(child: Text('Net ${tx['net_weight']} kg')),
              if (tx['rejected_reason'] != null)
                Center(child: Text('Rejected: ${tx['rejected_reason']}')),
              if (tx['rejected_reason'] == null &&
                  tx['pricing_status'] == 'priced')
                Center(
                  child: Text(
                    'Payable: ${tx['gross_amount']} ${tx['currency']}',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
              if (tx['rejected_reason'] == null &&
                  tx['pricing_status'] == 'priced')
                const Center(
                  child: Text('Will appear in the next supplier settlement.'),
                ),
              const SizedBox(height: 16),
              // --- The parchi (P1-MOBILE-COUNTER-001) -----------------------
              if (tx['offline'] == true)
                const Card(
                  child: Padding(
                    padding: EdgeInsets.all(16),
                    child: Text(
                      'The parchi is issued when this phone syncs — the slip '
                      'number comes from the platform, and this device will '
                      'not invent one.',
                    ),
                  ),
                )
              else if (_slip != null) ...[
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Parchi ${_slip!['slip_number']}',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        const SizedBox(height: 8),
                        Text(
                          '${_slip!['text']}',
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
                    await Clipboard.setData(
                      ClipboardData(text: '${_slip!['text']}'),
                    );
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Parchi copied')),
                    );
                  },
                ),
              ] else
                OutlinedButton.icon(
                  icon: const Icon(Icons.receipt_long_outlined),
                  label: Text(_slipBusy ? 'Fetching parchi…' : 'Get parchi'),
                  onPressed: _slipBusy ? null : _fetchSlip,
                ),
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
