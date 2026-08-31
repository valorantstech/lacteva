// The whole read-assist path, over a real socket (WO-49).
//
// Not a mocked transport: a real TCP server emits the frames a real
// instrument would, including the partial first frame every settling
// instrument sends, and the bridge has to get from bytes to an attributed
// reading without help.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/devices/device_bridge.dart';
import 'package:lacteva_mobile/src/devices/device_transport.dart';
import 'package:lacteva_mobile/src/devices/frame_profile.dart';

Future<ServerSocket> _instrument(List<String> frames) async {
  final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
  server.listen((socket) async {
    for (final frame in frames) {
      socket.write(frame);
      await socket.flush();
      await Future<void>.delayed(const Duration(milliseconds: 10));
    }
    await socket.close();
  });
  return server;
}

void main() {
  test('a settling instrument yields one attributed reading', () async {
    // The first frame is the partial one a real analyzer sends while settling.
    final server = await _instrument(['LACTEVA,,,\n', 'LACTEVA,4.20,8.45,27.5,1.029,4.0\n']);
    addTearDown(server.close);

    final bridge = DeviceBridge(
      deviceId: 'device-uuid-1',
      profile: simulatorAnalyzerProfile,
      transport: TcpDeviceTransport(host: server.address.address, port: server.port),
    );
    final reading = await bridge.read();

    expect(reading.values['fat'], 4.20);
    expect(reading.values['snf'], 8.45);
    expect(reading.deviceId, 'device-uuid-1');
    expect(reading.profileKey, 'lacteva-sim-analyzer-v1');
    // The digest, not the frame: the platform must be able to tie a disputed
    // reading to the bytes without holding the bytes.
    expect(reading.frameHash, startsWith('sha256:'));
    expect(reading.frameHash.length, 'sha256:'.length + 64);
  });

  test('the same frame always hashes the same, and a different one does not', () async {
    Future<String> hashOf(String frame) async {
      final server = await _instrument([frame]);
      addTearDown(server.close);
      final bridge = DeviceBridge(
        deviceId: 'd',
        profile: simulatorAnalyzerProfile,
        transport: TcpDeviceTransport(host: server.address.address, port: server.port),
      );
      return (await bridge.read()).frameHash;
    }

    const a = 'LACTEVA,4.20,8.45,27.5,1.029,4.0\n';
    const b = 'LACTEVA,4.30,8.45,27.5,1.029,4.0\n';
    expect(await hashOf(a), await hashOf(a));
    expect(await hashOf(a), isNot(await hashOf(b)));
  });

  test('an instrument that says nothing does not hang the operator', () async {
    // Spec §8: "the connector must never block the operator". A silent device
    // is the ordinary case — the operator types the numbers instead.
    final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((socket) {/* connected, and silent */});
    addTearDown(server.close);

    final bridge = DeviceBridge(
      deviceId: 'd',
      profile: simulatorAnalyzerProfile,
      transport: TcpDeviceTransport(host: server.address.address, port: server.port),
    );
    await expectLater(
      bridge.read(timeout: const Duration(milliseconds: 300)),
      throwsA(isA<DeviceTransportError>()),
    );
  });

  test('an unreachable instrument fails with something an operator can read', () async {
    final bridge = DeviceBridge(
      deviceId: 'd',
      profile: simulatorAnalyzerProfile,
      // Port 1 on loopback: nothing listens there.
      transport: TcpDeviceTransport(
        host: '127.0.0.1',
        port: 1,
        connectTimeout: const Duration(milliseconds: 300),
      ),
    );
    await expectLater(bridge.read(), throwsA(isA<DeviceTransportError>()));
  });

  test('a stream of only-unparseable frames never invents a reading', () async {
    final server = await _instrument(['GARBAGE\n', 'LACTEVA,x,y\n', 'nonsense\n']);
    addTearDown(server.close);

    final bridge = DeviceBridge(
      deviceId: 'd',
      profile: simulatorAnalyzerProfile,
      transport: TcpDeviceTransport(host: server.address.address, port: server.port),
    );
    await expectLater(
      bridge.read(timeout: const Duration(seconds: 2)),
      throwsA(isA<DeviceTransportError>()),
    );
  });
}
