/// Binding a registered instrument to this handset (WO-54).
///
/// The registry says a machine EXISTS at this centre; this screen says how
/// this phone reaches it. Until now `DeviceBinding` was constructed nowhere at
/// runtime — the read-assist path in the wizard was reachable only by a test,
/// which is the handset half of the same gap the portal's Devices card closes.
///
/// WHAT IS OFFERED, AND WHAT IS SAID INSTEAD.
///
/// TCP is offered because it works and is proven against a socket. Bluetooth
/// Classic, BLE and USB-OTG are named in plain words as awaiting bench
/// hardware — as TEXT, never as a disabled control. A greyed-out "Bluetooth"
/// button is a promise with a date nobody has set; a sentence saying the link
/// is not built yet is a fact somebody can plan around.
///
/// Profiles are restricted to the VERIFIED list, which today is the
/// simulator's own and is labelled as such. The guard in `frame_profile.dart`
/// stays: a profile written from memory for a real analyzer would mis-parse
/// silently, and marking it UNVERIFIED does not make the readings less wrong.
library;

import 'package:flutter/material.dart';

import '../api.dart';
import '../printing/escpos.dart';
import '../printing/printer_transport.dart';
import 'binding_store.dart';
import 'device_bridge.dart';
import 'device_settings.dart';
import 'device_transport.dart';
import 'frame_profile.dart';

/// The links a counter instrument might use, and their honest status.
const _linksAwaitingHardware = [
  ('Bluetooth Classic (SPP)', 'the common serial link on older analyzers'),
  ('Bluetooth Low Energy', 'newer handheld instruments'),
  ('USB-OTG serial', 'CH340, FTDI and CP210x cables'),
];

class InstrumentsScreen extends StatefulWidget {
  const InstrumentsScreen({
    super.key,
    required this.client,
    required this.centerId,
    required this.bindings,
    this.initialSettings,
  });

  final ApiClient client;
  final String centerId;
  final BindingStore bindings;
  final DeviceSettings? initialSettings;

  @override
  State<InstrumentsScreen> createState() => _InstrumentsScreenState();
}

class _InstrumentsScreenState extends State<InstrumentsScreen> {
  late DeviceSettings _settings = widget.initialSettings ?? const DeviceSettings();
  List<Map<String, dynamic>> _devices = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    Future.microtask(_load);
  }

  Future<void> _load() async {
    try {
      final rows = await widget.client.listCenterDevices(widget.centerId);
      final loaded = widget.initialSettings ?? await widget.bindings.load();
      if (!mounted) return;
      setState(() {
        _devices = rows.cast<Map<String, dynamic>>();
        _settings = loaded;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      // A registry the phone cannot read is not a centre with no instruments.
      setState(() {
        _error = 'Could not load this centre\'s devices. $e';
        _loading = false;
      });
    }
  }

  List<Map<String, dynamic>> _byCategory(String category) => _devices
      .where((d) => d['category'] == category && d['status'] == 'active')
      .toList();

  Future<void> _persist(DeviceSettings next) async {
    setState(() => _settings = next);
    await widget.bindings.save(next);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Instruments')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                if (_error != null) ...[
                  Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                  const SizedBox(height: 16),
                ],
                _BindingCard(
                  title: 'Analyzer',
                  category: 'milk_analyzer',
                  devices: _byCategory('milk_analyzer'),
                  binding: _settings.analyzer,
                  profiles: shippedProfiles
                      .where((p) => p.fieldMap.values.any(analyzerFields.contains))
                      .toList(),
                  onBind: (b) => _persist(
                    DeviceSettings(
                      analyzer: b,
                      scale: _settings.scale,
                      printer: _settings.printer,
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                _BindingCard(
                  title: 'Scale',
                  category: 'scale',
                  devices: _byCategory('scale'),
                  binding: _settings.scale,
                  profiles: shippedProfiles
                      .where((p) => p.fieldMap.values.any(scaleFields.contains))
                      .toList(),
                  onBind: (b) => _persist(
                    DeviceSettings(
                      analyzer: _settings.analyzer,
                      scale: b,
                      printer: _settings.printer,
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                _PrinterCard(
                  devices: _byCategory('printer'),
                  binding: _settings.printer,
                  onBind: (p) => _persist(
                    DeviceSettings(
                      analyzer: _settings.analyzer,
                      scale: _settings.scale,
                      printer: p,
                    ),
                  ),
                ),
                const SizedBox(height: 24),
                const _AwaitingHardware(),
              ],
            ),
    );
  }
}

/// The links that are not built, said as sentences (WO-54).
class _AwaitingHardware extends StatelessWidget {
  const _AwaitingHardware();

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).textTheme.bodySmall;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Other links', style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 8),
            Text(
              'Only a network connection is available today. These are not '
              'built yet — they need a real instrument on a bench to write and '
              'prove, and there is no date for that here.',
              style: muted,
            ),
            const SizedBox(height: 8),
            for (final (name, why) in _linksAwaitingHardware)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('· $name — $why', style: muted),
              ),
          ],
        ),
      ),
    );
  }
}

class _BindingCard extends StatefulWidget {
  const _BindingCard({
    required this.title,
    required this.category,
    required this.devices,
    required this.binding,
    required this.profiles,
    required this.onBind,
  });

  final String title;
  final String category;
  final List<Map<String, dynamic>> devices;
  final DeviceBinding? binding;
  final List<FrameProfile> profiles;
  final ValueChanged<DeviceBinding?> onBind;

  @override
  State<_BindingCard> createState() => _BindingCardState();
}

class _BindingCardState extends State<_BindingCard> {
  late final _host = TextEditingController(text: widget.binding?.host ?? '');
  late final _port = TextEditingController(text: '${widget.binding?.port ?? 9099}');
  String? _deviceId;
  String? _profileKey;
  String? _note;
  bool _testing = false;

  @override
  void initState() {
    super.initState();
    _deviceId = widget.binding?.deviceId ?? (widget.devices.isNotEmpty ? '${widget.devices.first['id']}' : null);
    _profileKey = widget.binding?.profile.key ?? (widget.profiles.isNotEmpty ? widget.profiles.first.key : null);
  }

  DeviceBinding? _compose() {
    final profile = _profileKey == null ? null : profileByKey(_profileKey!);
    final port = int.tryParse(_port.text.trim());
    if (_deviceId == null || profile == null || _host.text.trim().isEmpty || port == null) {
      return null;
    }
    final device = widget.devices.firstWhere(
      (d) => '${d['id']}' == _deviceId,
      orElse: () => const {},
    );
    return DeviceBinding(
      deviceId: _deviceId!,
      label: '${device['name'] ?? widget.title}',
      profile: profile,
      host: _host.text.trim(),
      port: port,
    );
  }

  /// Read once and SHOW it. Nothing is captured — this answers "is the cable
  /// right and does the profile fit this machine", which is a different
  /// question from "record this milk", and answering it against a real
  /// transaction would put a test reading into a farmer's payment.
  Future<void> _testRead() async {
    final binding = _compose();
    if (binding == null) {
      setState(() => _note = 'Choose a device and enter a host and port first.');
      return;
    }
    setState(() {
      _testing = true;
      _note = null;
    });
    try {
      final reading = await DeviceBridge(
        deviceId: binding.deviceId,
        profile: binding.profile,
        transport: TcpDeviceTransport(host: binding.host, port: binding.port),
      ).read();
      final values = reading.values.entries.map((e) => '${e.key} ${e.value}').join(' · ');
      setState(() => _note = '$values\nframe ${reading.frameHash}');
    } on DeviceTransportError catch (e) {
      setState(() => _note = e.message);
    } finally {
      if (mounted) setState(() => _testing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.devices.isEmpty) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(widget.title, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              const Text(
                'No active device of this kind is registered at this centre. '
                'Register it in the portal first; capture by hand works either way.',
              ),
            ],
          ),
        ),
      );
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              isExpanded: true,
              initialValue: _deviceId,
              decoration: const InputDecoration(labelText: 'Registered device'),
              items: [
                for (final d in widget.devices)
                  DropdownMenuItem(value: '${d['id']}', child: Text('${d['name']}')),
              ],
              onChanged: (v) => setState(() => _deviceId = v),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              isExpanded: true,
              initialValue: _profileKey,
              decoration: const InputDecoration(
                labelText: 'Frame profile',
                helperText: 'Only profiles proven against a capture',
              ),
              items: [
                for (final p in widget.profiles)
                  DropdownMenuItem(value: p.key, child: Text(p.label)),
              ],
              onChanged: (v) => setState(() => _profileKey = v),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _host,
                    decoration: const InputDecoration(labelText: 'Host'),
                  ),
                ),
                const SizedBox(width: 12),
                SizedBox(
                  width: 96,
                  child: TextField(
                    controller: _port,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Port'),
                  ),
                ),
              ],
            ),
            if (_note != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(_note!, style: Theme.of(context).textTheme.bodySmall),
              ),
            const SizedBox(height: 12),
            Row(
              children: [
                OutlinedButton(
                  onPressed: _testing ? null : _testRead,
                  child: Text(_testing ? 'Reading…' : 'Test read'),
                ),
                const SizedBox(width: 12),
                FilledButton(
                  onPressed: () {
                    final binding = _compose();
                    if (binding == null) {
                      setState(() => _note = 'Choose a device and enter a host and port first.');
                      return;
                    }
                    widget.onBind(binding);
                    setState(() => _note = 'Saved. The wizard will offer this instrument.');
                  },
                  child: const Text('Save'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _PrinterCard extends StatefulWidget {
  const _PrinterCard({
    required this.devices,
    required this.binding,
    required this.onBind,
  });

  final List<Map<String, dynamic>> devices;
  final PrinterBinding? binding;
  final ValueChanged<PrinterBinding?> onBind;

  @override
  State<_PrinterCard> createState() => _PrinterCardState();
}

class _PrinterCardState extends State<_PrinterCard> {
  late final _host = TextEditingController(text: widget.binding?.host ?? '');
  late final _port = TextEditingController(text: '${widget.binding?.port ?? 9100}');
  late bool _narrow = widget.binding?.narrowPaper ?? false;
  String? _deviceId;
  String? _note;
  bool _printing = false;

  @override
  void initState() {
    super.initState();
    _deviceId = widget.binding?.deviceId ??
        (widget.devices.isNotEmpty ? '${widget.devices.first['id']}' : null);
  }

  PrinterBinding? _compose() {
    final port = int.tryParse(_port.text.trim());
    if (_deviceId == null || _host.text.trim().isEmpty || port == null) return null;
    final device = widget.devices.firstWhere(
      (d) => '${d['id']}' == _deviceId,
      orElse: () => const {},
    );
    return PrinterBinding(
      deviceId: _deviceId!,
      label: '${device['name'] ?? 'Printer'}',
      host: _host.text.trim(),
      port: port,
      narrowPaper: _narrow,
    );
  }

  Future<void> _testPrint() async {
    final binding = _compose();
    if (binding == null) {
      setState(() => _note = 'Choose a printer and enter a host and port first.');
      return;
    }
    setState(() {
      _printing = true;
      _note = null;
    });
    try {
      // A real parchi shape with obviously-test content: an operator who finds
      // this on the roll must not mistake it for a farmer's receipt.
      await TcpPrinterTransport(host: binding.host, port: binding.port).send(
        renderSlip(
          const {
            'slip_number': 'TEST PRINT',
            'organization_name': 'Lacteva',
            'center_name': 'Printer test',
            'quantity': '0',
            'weight_unit': 'kg',
            'fat': '0.0',
            'snf': '0.0',
            'decision': 'NOT A RECEIPT',
          },
          width: binding.narrowPaper ? PaperWidth.mm58 : PaperWidth.mm80,
        ),
      );
      setState(() => _note = 'Sent. Check the paper.');
    } on PrinterError catch (e) {
      setState(() => _note = e.message);
    } finally {
      if (mounted) setState(() => _printing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.devices.isEmpty) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Text(
            'No active printer is registered at this centre. The parchi can '
            'still be copied and shared, which needs no hardware at all.',
          ),
        ),
      );
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Printer', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              isExpanded: true,
              initialValue: _deviceId,
              decoration: const InputDecoration(labelText: 'Registered printer'),
              items: [
                for (final d in widget.devices)
                  DropdownMenuItem(value: '${d['id']}', child: Text('${d['name']}')),
              ],
              onChanged: (v) => setState(() => _deviceId = v),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _host,
                    decoration: const InputDecoration(labelText: 'Host'),
                  ),
                ),
                const SizedBox(width: 12),
                SizedBox(
                  width: 96,
                  child: TextField(
                    controller: _port,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Port'),
                  ),
                ),
              ],
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: _narrow,
              onChanged: (v) => setState(() => _narrow = v),
              title: const Text('58 mm paper'),
              subtitle: const Text('Nothing on the network can detect the roll width'),
            ),
            if (_note != null)
              Text(_note!, style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 12),
            Row(
              children: [
                OutlinedButton(
                  onPressed: _printing ? null : _testPrint,
                  child: Text(_printing ? 'Printing…' : 'Test print'),
                ),
                const SizedBox(width: 12),
                FilledButton(
                  onPressed: () {
                    final binding = _compose();
                    if (binding == null) {
                      setState(() => _note = 'Choose a printer and enter a host and port first.');
                      return;
                    }
                    widget.onBind(binding);
                    setState(() => _note = 'Saved. Print appears on the parchi screen.');
                  },
                  child: const Text('Save'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
