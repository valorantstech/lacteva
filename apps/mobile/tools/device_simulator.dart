/// A development instrument, so the device path can be proven without one.
///
/// WO-49. Serves the frames `lib/src/devices/frame_profile.dart` describes,
/// over TCP, so the whole read-assist path — transport, framing, parsing,
/// hashing, provenance, capture — runs end to end against something that
/// behaves like an instrument.
///
/// IT IS NOT A MOCK OF A REAL DEVICE, and the distinction matters. It does not
/// claim to speak any manufacturer's protocol; it speaks a dialect this
/// repository invented and documented, which is why the profile that reads it
/// is the only one honestly marked verified. When D-16 puts a real analyzer on
/// a bench, its captured frames get their own profile — this one does not
/// become it.
///
///   dart tools/device_simulator.dart --port 9099 --kind analyzer
///
/// Refused in production the way the mock adapters are: it is a tool outside
/// `lib/`, it ships in no build, and the app refuses a simulator profile when
/// `LACTEVA_ALLOW_DEVICE_SIMULATOR` is not set (see build_flags.dart).
library;

import 'dart:async';
import 'dart:io';

Future<void> main(List<String> args) async {
  var port = 9099;
  var kind = 'analyzer';
  for (var i = 0; i < args.length - 1; i++) {
    if (args[i] == '--port') port = int.parse(args[i + 1]);
    if (args[i] == '--kind') kind = args[i + 1];
  }

  final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, port);
  stdout.writeln('device simulator ($kind) on ${server.address.address}:${server.port}');

  await for (final socket in server) {
    // A real analyzer streams while it settles: the first frames are partial
    // or empty, and only then does a complete record arrive. The simulator
    // does the same, so the bridge's skip-until-parseable behaviour is
    // exercised rather than assumed.
    unawaited(_serve(socket, kind));
  }
}

Future<void> _serve(Socket socket, String kind) async {
  try {
    socket.write('LACTEVA,,,\n');
    await Future<void>.delayed(const Duration(milliseconds: 40));
    if (kind == 'scale') {
      socket.write('LACTEVA,32.500,4.500\n');
    } else {
      socket.write('LACTEVA,4.20,8.45,27.5,1.029,4.0\n');
    }
    await socket.flush();
    await Future<void>.delayed(const Duration(milliseconds: 60));
  } finally {
    await socket.close();
  }
}
