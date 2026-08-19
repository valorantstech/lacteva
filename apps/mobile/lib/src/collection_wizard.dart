import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'build_flags.dart';
import 'l10n.dart';
import 'session.dart';

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
    this.session,
    this.initialStep = 0,
  });

  final ApiClient client;
  final String sessionId;

  /// The signed-in principal, for language only (P1-LOCALE-I18N-001).
  /// Null renders English — no test constructor changes needed.
  final Session? session;

  /// Which step to open on. Exists so a widget test can assert what a given
  /// step offers without driving five API round trips to reach it; the app
  /// always starts at 0.
  final int initialStep;

  @override
  State<CollectionWizardScreen> createState() => _CollectionWizardScreenState();
}

class _CollectionWizardScreenState extends State<CollectionWizardScreen> {
  L10n get _l => L10n.of(widget.session);

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
      setState(() => _error = _l.t('common.couldNotReach'));
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
    // Deliberately NOT localized (P1-LOCALE-I18N-001): mirrors the server's
    // own refusal wording so online and offline read identically. Localizing
    // both ends needs machine codes server-side — recorded TO CONFIRM.
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
      // Deliberately NOT localized (P1-LOCALE-I18N-001): mirrors the server's
      // own refusal wording so online and offline read identically. Localizing
      // both ends needs machine codes server-side — recorded TO CONFIRM.
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
        _error = _l.t('wizard.rejectWhy');
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
      if (mounted) setState(() => _error = _l.t('common.couldNotReach'));
    } finally {
      if (mounted) setState(() => _slipBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final tx = _tx;
    final t = _l;
    return Scaffold(
      appBar: AppBar(title: Text(t.t('wizard.stepTitle', {'n': _step + 1}))),
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
              Text(
                t.t('wizard.supplier'),
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _supplierCode,
                decoration: InputDecoration(
                  labelText: t.t('wizard.supplierCode'),
                  helperText: t.t('wizard.supplierCodeHelp'),
                ),
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : _identify,
                child: Text(t.t('wizard.identify')),
              ),
            ],
            if (_step == 1) ...[
              Text(
                t.t('wizard.milk'),
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _milkType,
                decoration: InputDecoration(labelText: t.t('wizard.milkType')),
                // The LABEL comes from the catalog; the VALUE sent to the API
                // stays the raw code (P1-LOCALE-I18N-001).
                items: const ['cow', 'buffalo', 'goat', 'mixed']
                    .map(
                      (m) =>
                          DropdownMenuItem(value: m, child: Text(t.t('milk.$m'))),
                    )
                    .toList(),
                onChanged: (v) => setState(() => _milkType = v ?? 'cow'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _containerType,
                decoration: InputDecoration(
                  labelText: t.t('wizard.containerType'),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _containerId,
                decoration: InputDecoration(
                  labelText: t.t('wizard.containerId'),
                ),
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : _milk,
                child: Text(t.t('wizard.receiveMilk')),
              ),
            ],
            if (_step == 2) ...[
              Text(
                t.t('wizard.weight'),
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _gross,
                decoration: InputDecoration(labelText: t.t('wizard.grossKg')),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _tare,
                decoration: InputDecoration(labelText: t.t('wizard.tareKg')),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : () => _weight(mock: false),
                child: Text(t.t('wizard.captureWeight')),
              ),
              // SEC-003 / F-01: absent from a release build, not hidden.
              if (kMockHardwareEnabled)
                TextButton(
                  onPressed: _busy ? null : () => _weight(mock: true),
                  child: Text(t.t('wizard.mockScale')),
                ),
            ],
            if (_step == 3) ...[
              Text(
                t.t('wizard.quality'),
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _fat,
                decoration: InputDecoration(labelText: t.t('wizard.fatLabel')),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _snf,
                decoration: InputDecoration(labelText: t.t('wizard.snfLabel')),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _clr,
                decoration: InputDecoration(labelText: t.t('wizard.clrLabel')),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : () => _quality(mock: false),
                child: Text(t.t('wizard.captureQuality')),
              ),
              if (kMockHardwareEnabled)
                TextButton(
                  onPressed: _busy ? null : () => _quality(mock: true),
                  child: Text(t.t('wizard.mockAnalyzer')),
                ),
            ],
            if (_step == 4 && tx != null) ...[
              Text(
                t.t('wizard.review'),
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 12),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        t.t('wizard.netWeightLine', {'kg': tx['net_weight']}),
                      ),
                      Text(
                        t.t('wizard.qualityLine', {
                          'fat': tx['fat'],
                          'snf': tx['snf'],
                          'clr': tx['clr'],
                        }),
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
                        Text(
                          t.t('wizard.pricingLine', {
                            'status': tx['pricing_status'],
                          }),
                        ),
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
                child: Text(t.t('wizard.acceptComplete')),
              ),
              if (!_rejecting)
                OutlinedButton(
                  onPressed: _busy
                      ? null
                      : () => setState(() => _rejecting = true),
                  child: Text(t.t('wizard.reject')),
                ),
              if (_rejecting) ...[
                const SizedBox(height: 12),
                TextField(
                  controller: _rejectReason,
                  decoration: InputDecoration(
                    labelText: t.t('wizard.rejectReason'),
                    helperText: t.t('wizard.rejectReasonHelp'),
                  ),
                ),
                const SizedBox(height: 8),
                OutlinedButton(
                  onPressed: _busy ? null : () => _decide(false),
                  child: Text(t.t('wizard.rejectComplete')),
                ),
                TextButton(
                  onPressed: _busy
                      ? null
                      : () => setState(() {
                          _rejecting = false;
                          _rejectReason.clear();
                        }),
                  child: Text(t.t('wizard.keepReviewing')),
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
                  // The STATE stays the raw server code (a {var}, never
                  // translated).
                  tx['offline'] == true
                      ? t.t('wizard.savedQueued')
                      : t.t('wizard.txState', {'state': tx['state']}),
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              Center(
                child: Text(t.t('wizard.netLine', {'kg': tx['net_weight']})),
              ),
              if (tx['rejected_reason'] != null)
                Center(
                  child: Text(
                    t.t('wizard.rejectedLine', {
                      'reason': tx['rejected_reason'],
                    }),
                  ),
                ),
              if (tx['rejected_reason'] == null &&
                  tx['pricing_status'] == 'priced')
                Center(
                  child: Text(
                    t.t('wizard.payable', {
                      'amount': tx['gross_amount'],
                      'currency': tx['currency'],
                    }),
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
              if (tx['rejected_reason'] == null &&
                  tx['pricing_status'] == 'priced')
                Center(child: Text(t.t('wizard.nextSettlement'))),
              const SizedBox(height: 16),
              // --- The parchi (P1-MOBILE-COUNTER-001) -----------------------
              if (tx['offline'] == true)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Text(t.t('wizard.parchiQueued')),
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
                          t.t('wizard.parchi', {
                            'number': _slip!['slip_number'],
                          }),
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
                  label: Text(t.t('wizard.copyParchi')),
                  onPressed: () async {
                    await Clipboard.setData(
                      ClipboardData(text: '${_slip!['text']}'),
                    );
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(content: Text(t.t('wizard.parchiCopied'))),
                    );
                  },
                ),
              ] else
                OutlinedButton.icon(
                  icon: const Icon(Icons.receipt_long_outlined),
                  label: Text(
                    _slipBusy
                        ? t.t('wizard.fetchingParchi')
                        : t.t('wizard.getParchi'),
                  ),
                  onPressed: _slipBusy ? null : _fetchSlip,
                ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: Text(t.t('common.done')),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
