// Bytes reaching a printer, over a real socket (WO-50).
import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/printing/escpos.dart';
import 'package:lacteva_mobile/src/printing/printer_transport.dart';

void main() {
  test('the document arrives at the sink byte for byte', () async {
    final received = <int>[];
    final done = Completer<void>();
    final sink = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(sink.close);
    sink.listen((socket) {
      socket.listen(received.addAll, onDone: () {
        if (!done.isCompleted) done.complete();
      });
    });

    final bytes = renderSlip(const {
      'slip_number': 'SLP-1',
      'organization_name': 'Dairy',
      'center_name': 'Centre',
      'quantity': '10',
      'weight_unit': 'kg',
      'fat': '4.0',
      'snf': '8.0',
      'decision': 'ACCEPTED',
    });
    await TcpPrinterTransport(host: sink.address.address, port: sink.port).send(bytes);
    await done.future.timeout(const Duration(seconds: 5));

    expect(received, bytes, reason: 'the printer received something other than the document');
  });

  test('an unreachable printer says so, and says where', () async {
    // The operator needs to know WHICH printer failed, because the answer is
    // usually that it is switched off.
    final transport = TcpPrinterTransport(
      host: '127.0.0.1',
      port: 1,
      timeout: const Duration(milliseconds: 300),
    );
    await expectLater(
      transport.send([0x1B, 0x40]),
      throwsA(isA<PrinterError>().having((e) => e.message, 'message', contains('127.0.0.1:1'))),
    );
  });
}
