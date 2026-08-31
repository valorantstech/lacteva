// Getting the rendered bytes to a printer (WO-50).
//
// The same shape as the device transports, and for the same reason: three of
// the four links a counter printer might use — Bluetooth Classic, BLE, USB —
// need platform plugins and a physical printer to exercise, and shipping code
// that has never moved a byte into the app an operator uses at a counter is
// the failure this repository is built to avoid. TCP port 9100 is implemented
// and proven against a real socket; the rest land with D-16's bench printer,
// against this interface, and nothing above them changes.
//
// D-16 SEAM: an implementation of `PrinterTransport` per link, plus the
// address on the registered Device, is the whole remaining job.
library;

import 'dart:async';
import 'dart:io';

abstract class PrinterTransport {
  String get description;

  /// Send one complete document. Returns when the printer has taken it.
  Future<void> send(List<int> bytes);
}

class PrinterError implements Exception {
  PrinterError(this.message);
  final String message;
  @override
  String toString() => 'PrinterError: $message';
}

/// A network thermal printer, or any print server, on the RAW/JetDirect port.
///
/// Port 9100 is the near-universal default for network receipt printers, and
/// the protocol is "open a socket, write the bytes, close it" — there is no
/// acknowledgement to wait for, which is why a successful send proves the
/// printer ACCEPTED the job and not that paper came out. The operator seeing
/// no slip is the only real confirmation, which is why the share sheet stays.
class TcpPrinterTransport implements PrinterTransport {
  TcpPrinterTransport({
    required this.host,
    this.port = 9100,
    this.timeout = const Duration(seconds: 8),
  });

  final String host;
  final int port;
  final Duration timeout;

  @override
  String get description => 'printer at $host:$port';

  @override
  Future<void> send(List<int> bytes) async {
    Socket? socket;
    try {
      socket = await Socket.connect(host, port, timeout: timeout);
      socket.add(bytes);
      await socket.flush().timeout(timeout);
    } on SocketException catch (e) {
      throw PrinterError('could not reach $description — ${e.osError?.message ?? e.message}');
    } on TimeoutException {
      throw PrinterError('$description accepted the connection but not the job');
    } finally {
      socket?.destroy();
    }
  }
}
