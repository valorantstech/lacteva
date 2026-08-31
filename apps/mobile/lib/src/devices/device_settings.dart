/// Where the handset can reach a centre's instruments (WO-49).
///
/// AN OPEN DESIGN QUESTION, recorded rather than quietly decided. The `Device`
/// registry row is the identity anchor (spec §9) and carries category, serial,
/// status and centre — but no transport address, because until now nothing
/// connected to a device. A TCP bridge needs a host and port; Bluetooth needs
/// a MAC or a BLE id.
///
/// This keeps that binding on the HANDSET rather than adding a column, for two
/// reasons. The address is a property of the local network the phone is
/// standing on, not of the device as the platform knows it — the same analyzer
/// behind a different bridge has a different address and is the same device.
/// And spec §14 says read-assist needs no schema change; inventing one here,
/// before a single real instrument has been connected, would be deciding the
/// shape of a field from a guess about what real hardware needs. When D-16 puts
/// devices on a bench, what they actually need to be addressed by is evidence,
/// and the registry can carry it then.
library;

import 'frame_profile.dart';

/// A registered device this handset knows how to reach.
class DeviceBinding {
  const DeviceBinding({
    required this.deviceId,
    required this.label,
    required this.profile,
    required this.host,
    required this.port,
  });

  final String deviceId;
  final String label;
  final FrameProfile profile;
  final String host;
  final int port;
}

/// The bindings this handset holds, by device category.
///
/// In-memory and injected, so the wizard has no opinion about where they come
/// from and a test can supply one without a device.
class DeviceSettings {
  const DeviceSettings({this.analyzer, this.scale});

  final DeviceBinding? analyzer;
  final DeviceBinding? scale;

  bool get hasAnalyzer => analyzer != null;
  bool get hasScale => scale != null;
}
