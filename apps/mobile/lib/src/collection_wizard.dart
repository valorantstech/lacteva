import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'brand/motion.dart';
import 'build_flags.dart';
import 'l10n.dart';
import 'session.dart';
import 'theme.dart';
import 'devices/device_bridge.dart';
import 'devices/device_settings.dart';
import 'devices/device_transport.dart';
import 'offline/offline_client.dart';
import 'printing/escpos.dart';
import 'printing/printer_transport.dart';

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
/// A reading taken from an instrument, and still untouched by the operator.
///
/// The moment a device-filled value is EDITED it stops being the device's
/// reading, so the provenance is dropped and the capture goes up as manual.
/// Anything else would attribute a hand-corrected number to a machine, which
/// is the fabrication spec §7 exists to make visible.
class _AssistedReading {
  const _AssistedReading(this.reading, this.filled);
  final DeviceReading reading;
  final Map<String, String> filled;

  bool stillMatches(Map<String, TextEditingController> fields) =>
      filled.entries.every((e) => fields[e.key]?.text.trim() == e.value);
}

class CollectionWizardScreen extends StatefulWidget {
  const CollectionWizardScreen({
    super.key,
    required this.client,
    required this.sessionId,
    this.session,
    this.initialStep = 0,
    this.devices = const DeviceSettings(),
    this.initialTransaction,
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

  /// WO-49: which instruments this handset can reach. Empty by default —
  /// manual capture is the first-class path and needs nothing.
  final DeviceSettings devices;

  /// A transaction to open on, so a test can reach a late step without
  /// driving every earlier one. The same seam `initialStep` already is.
  final Map<String, dynamic>? initialTransaction;

  @override
  State<CollectionWizardScreen> createState() => _CollectionWizardScreenState();
}

class _CollectionWizardScreenState extends State<CollectionWizardScreen> {
  /// The last analyzer/scale reading, while it is still the device's.
  _AssistedReading? _assistedQuality;
  _AssistedReading? _assistedWeight;
  String? _deviceNote;
  String? _printNote;
  bool _printing = false;
  bool _reading = false;

  L10n get _l => L10n.of(widget.session);

  late int _step = widget.initialStep;
  String? _txId;
  late Map<String, dynamic>? _tx = widget.initialTransaction;
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

  /// Ask an instrument for a reading and pre-fill the operator's fields.
  ///
  /// Read-assist (spec §5): the numbers land in the same boxes the operator
  /// types into, and the operator confirms them. A failure is not an error
  /// state — it is the ordinary case at a centre whose analyzer is off, so it
  /// leaves a note beside fields that stay perfectly usable.
  /// Whether this operator may change what the milk is worth (BR-0029).
  ///
  /// The permission list from `/v1/auth/me` is the authority. A control that
  /// is merely DISABLED still tells the person at the counter that the
  /// capability exists and they are not trusted with it, which is a different
  /// and worse message than a screen that simply does not offer it.
  bool get _mayOverrideRate => widget.session?.can('pricing.rate.override') ?? false;

  /// Why a rate override cannot be captured without a connection (WO-51b).
  ///
  /// Not a limitation to apologise for — a consequence of where pricing
  /// happens. The rate is resolved by the platform when quality is captured,
  /// so a collection queued offline has no resolved rate yet, and an
  /// "override" of a number that does not exist is not an override. The
  /// offline queue also carries no kind for it, deliberately: every kind maps
  /// one-to-one onto an online endpoint (OFF-001), and adding one that
  /// decided a price on the handset would put pricing in the client, which is
  /// the one thing capture must never do.
  ///
  /// So the screen says this, and refuses. It does not queue something that
  /// will fail later, and it does not pretend the rate changed.
  static const _offlineOverrideReason =
      'A rate change needs a connection: the rate is resolved by the platform '
      'when quality is captured, so there is nothing to override until this '
      'collection has synced.';

  bool get _offline {
    final client = widget.client;
    return client is OfflineApiClient && !client.isOnline;
  }

  Future<void> _editRate(Map<String, dynamic> tx) async {
    final rateController = TextEditingController(text: '${tx['unit_price'] ?? ''}');
    final reasonController = TextEditingController();
    final base = '${tx['base_unit_price'] ?? tx['unit_price'] ?? ''}';
    final currency = '${tx['currency'] ?? ''}';
    String? problem;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => AlertDialog(
          title: const Text('Edit rate'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (_offline)
                Text(_offlineOverrideReason, style: Theme.of(context).textTheme.bodyMedium)
              else ...[
                // Both numbers, before anything is confirmed: whoever changes
                // a farmer's rate should see what they are changing it FROM.
                Text('Card rate: $base $currency/kg'),
                const SizedBox(height: 12),
                TextField(
                  controller: rateController,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: InputDecoration(labelText: 'New rate ($currency/kg)'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: reasonController,
                  maxLines: 2,
                  decoration: const InputDecoration(
                    labelText: 'Reason (required)',
                    helperText: 'Shown on the parchi and in the audit trail',
                  ),
                ),
                if (problem != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      problem!,
                      style: TextStyle(color: Theme.of(context).colorScheme.error),
                    ),
                  ),
              ],
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('Cancel'),
            ),
            if (!_offline)
              FilledButton(
                onPressed: () {
                  final rate = double.tryParse(rateController.text.trim());
                  final reason = reasonController.text.trim();
                  // The same two refusals the platform makes, made here first
                  // so the operator is told before a round trip — never
                  // INSTEAD of the platform, which refuses them regardless.
                  if (rate == null || rate <= 0) {
                    setDialogState(() => problem = 'Enter a rate greater than zero');
                    return;
                  }
                  if (reason.length < 3) {
                    setDialogState(() => problem = 'A reason is required');
                    return;
                  }
                  Navigator.of(dialogContext).pop(true);
                },
                child: const Text('Change rate'),
              ),
          ],
        ),
      ),
    );

    if (confirmed != true) return;
    await _run(
      () => widget.client.txStep(
        '/v1/milk-transactions/$_txId/override-rate',
        body: {
          'unit_price': rateController.text.trim(),
          'reason': reasonController.text.trim(),
        },
      ),
    );
  }

  /// Send the parchi to the centre's printer (WO-50).
  ///
  /// A failure is reported and nothing else changes: the slip is already
  /// minted and durable, the text is on screen, and copying it is one tap
  /// away. Spec §10 — "printer down: fall back"; the record does not depend
  /// on the paper.
  Future<void> _printSlip() async {
    final printer = widget.devices.printer;
    final slip = _slip;
    if (printer == null || slip == null) return;
    setState(() {
      _printNote = null;
      _printing = true;
    });
    try {
      final bytes = renderSlip(
        slip,
        width: printer.narrowPaper ? PaperWidth.mm58 : PaperWidth.mm80,
      );
      await TcpPrinterTransport(host: printer.host, port: printer.port).send(bytes);
      setState(() => _printNote = 'Sent to ${printer.label}.');
    } on PrinterError catch (e) {
      setState(() => _printNote = '${e.message}. Copy the parchi instead.');
    } finally {
      if (mounted) setState(() => _printing = false);
    }
  }

  /// The read-assist control, above the fields it fills.
  ///
  /// Present only when this handset actually has a binding for the
  /// instrument: an operator at a centre with no analyzer should not see a
  /// button that can only disappoint them.
  Widget _readAssist({required bool quality}) {
    final binding = quality ? widget.devices.analyzer : widget.devices.scale;
    if (binding == null) return const SizedBox.shrink();
    final note = _deviceNote;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OutlinedButton.icon(
          onPressed: (_busy || _reading) ? null : () => _readFromDevice(quality: quality),
          icon: const Icon(Icons.sensors),
          label: Text(_reading ? 'Reading…' : 'Read from ${binding.label}'),
        ),
        if (note != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(note, style: Theme.of(context).textTheme.bodySmall),
          ),
        const SizedBox(height: 12),
      ],
    );
  }

  Future<void> _readFromDevice({required bool quality}) async {
    final binding = quality ? widget.devices.analyzer : widget.devices.scale;
    if (binding == null) return;
    setState(() {
      _reading = true;
      _deviceNote = null;
      _error = null;
    });
    try {
      final bridge = DeviceBridge(
        deviceId: binding.deviceId,
        profile: binding.profile,
        transport: TcpDeviceTransport(host: binding.host, port: binding.port),
      );
      final reading = await bridge.read();
      final filled = <String, String>{};
      void put(String field, TextEditingController controller) {
        final value = reading.values[field];
        if (value == null) return;
        controller.text = value.toString();
        filled[field] = controller.text.trim();
      }

      if (quality) {
        put('fat', _fat);
        put('snf', _snf);
        put('clr', _clr);
      } else {
        put('gross', _gross);
        put('tare', _tare);
      }
      setState(() {
        final assisted = _AssistedReading(reading, filled);
        if (quality) {
          _assistedQuality = assisted;
        } else {
          _assistedWeight = assisted;
        }
        _deviceNote = 'Read from ${binding.label}. Check the numbers before you continue.';
      });
    } on DeviceTransportError catch (e) {
      // Never blocking: the manual fields are right there.
      setState(() => _deviceNote = '${e.message}. Enter the reading by hand.');
    } finally {
      if (mounted) setState(() => _reading = false);
    }
  }

  /// The provenance to send, if the device's numbers are still the device's.
  Map<String, Object?> _provenanceFor(
    _AssistedReading? assisted,
    Map<String, TextEditingController> fields,
    String instrumentSource,
  ) {
    return provenanceFor(
      reading: assisted?.reading,
      filled: assisted?.filled ?? const {},
      current: {for (final e in fields.entries) e.key: e.value.text},
      instrumentSource: instrumentSource,
    );
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
          if (mock) 'source': 'mock_scale',
          if (!mock) ..._provenanceFor(_assistedWeight, {'gross': _gross, 'tare': _tare}, 'scale'),
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
          if (mock) 'source': 'mock_analyzer',
          if (!mock)
            ..._provenanceFor(
              _assistedQuality,
              {'fat': _fat, 'snf': _snf, 'clr': _clr},
              'analyzer',
            ),
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
                // WO-55: the platform's own MILK_TYPES, in full.
                items: const ['cow', 'buffalo', 'goat', 'sheep', 'mixed']
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
              _readAssist(quality: false),
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
              _readAssist(quality: true),
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
                        // BR-0029 / D-3. Once a rate has been changed, this
                        // screen shows BOTH numbers and the reason — the same
                        // thing the parchi and the portal show, because an
                        // override that is only visible in one place is one
                        // somebody can miss.
                        if (tx['base_unit_price'] != null) ...[
                          const SizedBox(height: 4),
                          Text(
                            'Card rate ${tx['base_unit_price']} ${tx['currency']}/kg '
                            '· changed: ${tx['override_reason'] ?? ''}',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ],
                        // Absent, not disabled, for anyone without the
                        // permission: a greyed-out control still tells the
                        // person at the counter that the capability exists
                        // and they are not trusted with it.
                        if (_mayOverrideRate)
                          TextButton.icon(
                            icon: const Icon(Icons.edit_outlined),
                            label: const Text('Edit rate'),
                            onPressed: _busy ? null : () => _editRate(tx),
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
              // Panel 5: a save confirms with a tick inside ONE milk ripple.
              // A rejection does not ripple — a ripple is a celebration, and
              // milk that was refused is not one.
              if (tx['rejected_reason'] == null)
                Center(
                  child: SuccessRipple(
                    size: 72,
                    label: t.t('wizard.txState', {'state': tx['state']}),
                  ),
                )
              else
                const Icon(Icons.cancel, size: 72, color: LactevaColors.danger),
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
                ParchiMint(
                  child: Card(
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
                ),
                // WO-50: offered only where a printer is registered. Copying
                // the parchi sits beside it and always works — the farmer's
                // copy must never depend on a machine being switched on.
                if (widget.devices.hasPrinter)
                  FilledButton.tonalIcon(
                    icon: const Icon(Icons.print_outlined),
                    label: Text(_printing ? 'Printing…' : 'Print parchi'),
                    onPressed: _printing ? null : _printSlip,
                  ),
                if (_printNote != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(_printNote!, style: Theme.of(context).textTheme.bodySmall),
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
