/// Which registered device this handset can reach, and how (WO-54).
///
/// A binding is a LOCAL fact, and that is a deliberate boundary rather than a
/// shortcut. The `Device` row is the identity anchor — tenant, centre,
/// category, serial, lifecycle — and it is the same row on every phone in the
/// dairy. The address is not: the analyzer behind a WiFi bridge answers on one
/// IP from the operator's handset and possibly another from the manager's, and
/// the same instrument moved to a different bridge is the same device at a new
/// address. Storing that on the server would make one phone's network the
/// dairy's, and `device_settings.dart` records why the registry does not carry
/// it: what real hardware needs to be addressed by is evidence D-16 has yet to
/// produce.
///
/// So bindings live beside the offline queue, in the same atomic-write store,
/// and survive a restart the same way a morning's collections do.
library;

import '../offline/store.dart';
import 'device_settings.dart';
import 'frame_profile.dart';

class BindingStore {
  BindingStore(this._store);

  final OfflineStore _store;

  static const _key = 'device_bindings';

  Future<DeviceSettings> load() async {
    final data = await _store.read();
    final raw = data?[_key];
    if (raw is! Map) return const DeviceSettings();
    return DeviceSettings(
      analyzer: _binding(raw['analyzer']),
      scale: _binding(raw['scale']),
      printer: _printer(raw['printer']),
    );
  }

  Future<void> save(DeviceSettings settings) async {
    final data = await _store.read() ?? <String, dynamic>{};
    data[_key] = {
      if (settings.analyzer != null) 'analyzer': _bindingJson(settings.analyzer!),
      if (settings.scale != null) 'scale': _bindingJson(settings.scale!),
      if (settings.printer != null)
        'printer': {
          'device_id': settings.printer!.deviceId,
          'label': settings.printer!.label,
          'host': settings.printer!.host,
          'port': settings.printer!.port,
          'narrow_paper': settings.printer!.narrowPaper,
        },
    };
    await _store.write(data);
  }

  static DeviceBinding? _binding(Object? raw) {
    if (raw is! Map) return null;
    // An unknown profile key means the app was downgraded, or a profile was
    // withdrawn because it was never verified. Dropping the binding is the
    // safe direction: no reading is better than one parsed by a guess.
    final profile = profileByKey('${raw['profile']}');
    if (profile == null) return null;
    return DeviceBinding(
      deviceId: '${raw['device_id']}',
      label: '${raw['label']}',
      profile: profile,
      host: '${raw['host']}',
      port: raw['port'] is int ? raw['port'] as int : 0,
    );
  }

  static PrinterBinding? _printer(Object? raw) {
    if (raw is! Map) return null;
    return PrinterBinding(
      deviceId: '${raw['device_id']}',
      label: '${raw['label']}',
      host: '${raw['host']}',
      port: raw['port'] is int ? raw['port'] as int : 9100,
      narrowPaper: raw['narrow_paper'] == true,
    );
  }

  static Map<String, dynamic> _bindingJson(DeviceBinding b) => {
    'device_id': b.deviceId,
    'label': b.label,
    'profile': b.profile.key,
    'host': b.host,
    'port': b.port,
  };
}
