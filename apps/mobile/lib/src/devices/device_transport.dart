/// How bytes get from an instrument to the handset (WO-49).
///
/// Four transports are named by the work order — Bluetooth Classic (SPP),
/// BLE, USB-OTG serial (CH340/FTDI/CP210x) and a TCP socket for RS-232→WiFi
/// bridges. This file defines the seam all four share and implements the one
/// that can be proven today.
///
/// WHY ONLY TCP IS IMPLEMENTED. The other three need platform plugins and a
/// physical radio or cable to exercise; nothing in CI, and no device on any
/// desk here, can make a single assertion about them. Shipping three
/// unexercised transports into the app an operator uses at a counter would put
/// code on the critical path of a farmer being paid that has never moved a
/// byte — which is the failure mode this repository was built around. TCP runs
/// against the simulator over a real socket in a real test, so it is the one
/// that earns its place. The remaining three land with D-16's bench hardware,
/// against this same interface, and the wizard, bridge and profiles above them
/// do not change when they do.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// What every transport must be, and nothing more: a stream of complete frames.
///
/// Framing belongs here rather than in the parser because it is a property of
/// the LINK — a BLE characteristic delivers chunks, a socket delivers a byte
/// stream, and both must become whole records before anything tries to read a
/// fat value out of them.
abstract class DeviceTransport {
  /// Human-readable, for the operator's screen when it fails.
  String get description;

  /// Complete frames, terminator excluded. Closes when the link closes.
  Stream<String> frames();

  Future<void> close();
}

class DeviceTransportError implements Exception {
  DeviceTransportError(this.message);
  final String message;
  @override
  String toString() => 'DeviceTransportError: $message';
}

/// An instrument reached over TCP: an RS-232→WiFi bridge, or the simulator.
///
/// The common field pattern — a serial instrument behind a cheap WiFi bridge
/// on a fixed port — is exactly what this speaks, so it is not simulator-only
/// scaffolding even though the simulator is what proves it here.
class TcpDeviceTransport implements DeviceTransport {
  TcpDeviceTransport({
    required this.host,
    required this.port,
    this.terminator = '\n',
    this.connectTimeout = const Duration(seconds: 5),
  });

  final String host;
  final int port;
  final String terminator;
  final Duration connectTimeout;

  Socket? _socket;

  @override
  String get description => 'TCP $host:$port';

  @override
  Stream<String> frames() async* {
    final Socket socket;
    try {
      socket = await Socket.connect(host, port, timeout: connectTimeout);
    } on SocketException catch (e) {
      // Never a crash and never a hang: spec §8 says a connector "must never
      // block the operator" — read-assist times out and the manual fields stay
      // usable. The wizard turns this into a message beside the fields the
      // operator can simply type into.
      throw DeviceTransportError('could not reach $host:$port — ${e.osError?.message ?? e.message}');
    }
    _socket = socket;
    var buffer = '';
    await for (final chunk in socket.cast<List<int>>().transform(utf8.decoder)) {
      buffer += chunk;
      var index = buffer.indexOf(terminator);
      while (index != -1) {
        final frame = buffer.substring(0, index);
        buffer = buffer.substring(index + terminator.length);
        if (frame.trim().isNotEmpty) yield frame;
        index = buffer.indexOf(terminator);
      }
    }
  }

  @override
  Future<void> close() async {
    // `destroy()`, not `close()`. A graceful close half-shuts the connection
    // and waits for the peer to finish — and a silent instrument never does,
    // so the wait outlives the read and the operator's screen never comes
    // back. Tearing the socket down is what "the connector must never block
    // the operator" (spec §8) means in code.
    _socket?.destroy();
    _socket = null;
  }
}
