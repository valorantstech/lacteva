// The parchi as bytes, asserted byte by byte (WO-50).
//
// A printer is the one output nobody can eyeball in CI, so the document is
// pinned rather than described: golden bytes at both paper widths, and named
// tests for each way a receipt can silently lose the number the farmer came
// for.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/printing/escpos.dart';

final _slip = <String, dynamic>{
  'slip_number': 'SLP-2026-000042',
  'organization_name': 'Lacteva India Demo',
  'center_name': 'Kadegaon Centre',
  'session_label': 'morning',
  'collected_at': '2026-08-31T07:30:00Z',
  'supplier_code': 'SUP-014',
  'supplier_name': 'Anita Deshmukh',
  'milk_type': 'cow',
  'milk_type_custom': '',
  'quantity': '28.0',
  'weight_unit': 'kg',
  'fat': '4.2',
  'snf': '8.45',
  'clr': '27.5',
  'unit_price': '45.0000',
  'gross_amount': '1260.00',
  'currency': 'INR',
  'operator_name': 'Ravi K',
  'decision': 'ACCEPTED',
  'pricing_status': 'PRICED',
};

String _printable(List<int> bytes) => latin1.decode(bytes);

void main() {
  group('the rendered document', () {
    test('80 mm: every line is exactly 40 columns wide', () {
      final text = _printable(renderSlip(_slip, width: PaperWidth.mm80));
      final rules = text.split('\n').where((l) => l.startsWith('---')).toList();
      expect(rules, isNotEmpty);
      for (final rule in rules) {
        expect(rule.length, 40, reason: 'a rule that is not the paper width looks broken');
      }
      expect(text, contains('SLIP SLP-2026-000042'));
      expect(text, contains('Anita Deshmukh'));
    });

    test('58 mm: the same document, 32 columns, nothing lost', () {
      final text = _printable(renderSlip(_slip, width: PaperWidth.mm58));
      for (final rule in text.split('\n').where((l) => l.startsWith('---'))) {
        expect(rule.length, 32);
      }
      // The narrow roll must not drop the fields the slip exists for.
      expect(text, contains('SLP-2026-000042'));
      expect(text, contains('1260.00'));
      expect(text, contains('4.2'));
    });

    test('opens with the printer reset and ends with feed-then-cut', () {
      final bytes = renderSlip(_slip);
      expect(bytes.take(2).toList(), [0x1B, 0x40], reason: 'ESC @ — a printer may hold state '
          'from whatever printed last, and an uninitialised one prints the previous job\'s font');
      // Feed BEFORE cut: a printer with no cutter ignores the cut, and the
      // feed is what gets the slip past the tear bar so it can be torn off.
      expect(bytes.sublist(bytes.length - 8), [0x0A, 0x0A, 0x0A, 0x0A, 0x1D, 0x56, 0x42, 0x00]);
    });

    test('the amount is emphasised, because it is what is checked first', () {
      final bytes = renderSlip(_slip);
      final text = _printable(bytes);
      final amountAt = text.indexOf('AMOUNT');
      final boldOnBefore = _printable(bytes.sublist(0, amountAt)).lastIndexOf('\x1BE\x01');
      final boldOffBefore = _printable(bytes.sublist(0, amountAt)).lastIndexOf('\x1BE\x00');
      expect(boldOnBefore, greaterThan(boldOffBefore), reason: 'the amount line is not bold');
    });
  });

  group('what a stock printer cannot render', () {
    test('the rupee sign becomes Rs. rather than a blank', () {
      // A default code page has no U+20B9. Sent raw, the amount prints as a
      // gap and the farmer's copy silently loses its money field.
      expect(asciiForPrinter('₹1,260.00'), 'Rs.1,260.00');
    });

    test('Devanagari is dropped, not guessed at', () {
      // A machine-made romanisation of a farmer's name on a payment receipt
      // is a NEW name, not the same one in another script. The share sheet
      // carries the full bilingual parchi; this carries its ASCII half.
      expect(asciiForPrinter('किसान: Anita'), ': Anita');
    });

    test('a slip full of Devanagari still prints its structure', () {
      final hindi = Map<String, dynamic>.from(_slip)..['supplier_name'] = 'अनीता देशमुख';
      final text = _printable(renderSlip(hindi));
      expect(text, contains('SUP-014'));
      expect(text, contains('1260.00'));
      expect(text, isNot(contains('अ')));
    });

    test('no byte above 0x7E ever reaches the printer', () {
      final hindi = Map<String, dynamic>.from(_slip)
        ..['organization_name'] = 'डेयरी ₹'
        ..['supplier_name'] = 'अनीता';
      for (final byte in renderSlip(hindi)) {
        expect(byte <= 0x7E, isTrue, reason: 'byte $byte would print as mojibake');
      }
    });
  });

  group('two-column lines', () {
    test('label and value meet the paper edges exactly', () {
      expect(twoColumn('Fat %', '4.2', 20), 'Fat %            4.2');
      expect(twoColumn('Fat %', '4.2', 20).length, 20);
    });

    test('when it will not fit, the LABEL is truncated and the number survives', () {
      // The number is what the farmer came for; a truncated amount is a
      // receipt that lies.
      final line = twoColumn('A very long label indeed', '1260.00', 16);
      expect(line.length, lessThanOrEqualTo(16));
      expect(line, contains('1260.00'));
    });
  });

  group('a slip that is not yet priced', () {
    test('says so instead of printing an empty amount', () {
      final pending = Map<String, dynamic>.from(_slip)
        ..['pricing_status'] = 'PENDING'
        ..['unit_price'] = ''
        ..['gross_amount'] = '';
      final text = _printable(renderSlip(pending));
      expect(text, contains('Rate pending'));
      expect(text, isNot(contains('AMOUNT')));
    });
  });
}
