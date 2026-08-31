// The parchi, as bytes a thermal printer will accept (WO-50).
//
// WHAT THIS IS AND IS NOT PROVEN AGAINST. Every byte below is asserted by
// golden tests, so the DOCUMENT is proven. No physical printer has printed it:
// D-16 is the bench hardware, and until one exists the honest claim is "the
// renderer is correct", not "printing works". The transport seam is written so
// the day a printer arrives, only `EscPosTransport` needs a new implementation.
//
// WHY BYTES AND NOT THE SLIP'S OWN TEXT. The server already composes a
// shareable plain-text parchi, and the share sheet sends exactly that. A
// thermal printer needs more than text: a column width it cannot infer,
// emphasis for the fields a farmer checks first, a paper feed past the tear
// bar, and a cut. So this renders the STRUCTURED slip — the same fields, laid
// out for 40 or 32 columns — and the text stays the fallback that needs no
// hardware at all.
library;

import 'dart:convert';

/// ESC/POS control sequences, named rather than scattered as magic bytes.
class _Esc {
  static const init = [0x1B, 0x40]; // ESC @
  static const boldOn = [0x1B, 0x45, 0x01];
  static const boldOff = [0x1B, 0x45, 0x00];
  static const alignLeft = [0x1B, 0x61, 0x00];
  static const alignCentre = [0x1B, 0x61, 0x01];
  static const doubleHeight = [0x1D, 0x21, 0x01];
  static const normalSize = [0x1D, 0x21, 0x00];

  /// GS V 66 0 — feed then partial cut. Printers without a cutter ignore it,
  /// which is why the feed comes first: on those, the paper still clears the
  /// tear bar and the farmer can take the slip.
  static const feedAndCut = [0x0A, 0x0A, 0x0A, 0x0A, 0x1D, 0x56, 0x42, 0x00];
}

/// Paper widths in characters, at the standard 12×24 font.
enum PaperWidth {
  /// 80 mm paper.
  mm80(40),

  /// 58 mm paper — the common cheap counter printer.
  mm58(32);

  const PaperWidth(this.columns);
  final int columns;
}

/// What a stock thermal printer can render, from what the platform stores.
///
/// A default ESC/POS printer prints one byte per glyph out of a code page that
/// has no Devanagari and no rupee sign. Sending either produces mojibake or a
/// blank — the farmer's copy silently loses the amount, which is worse than
/// printing it plainly. So:
///
///   * `₹` becomes `Rs.` — the abbreviation Indian receipts used before the
///     glyph existed, and still use on plain printers.
///   * Any other non-ASCII rune is dropped rather than guessed at. A slip in
///     Hindi therefore prints its ASCII half; the SHARE sheet, which has no
///     such limit, remains the way to send the full bilingual parchi, and the
///     print button never becomes the only path to the document.
///
/// Transliterating Devanagari into Latin was considered and rejected: a
/// machine-made romanisation of a farmer's name on a payment receipt is a new
/// name, not the same one in another script.
String asciiForPrinter(String value) {
  final buffer = StringBuffer();
  for (final rune in value.runes) {
    if (rune == 0x20B9) {
      buffer.write('Rs.');
    } else if (rune >= 0x20 && rune <= 0x7E) {
      buffer.writeCharCode(rune);
    } else if (rune == 0x00A0) {
      buffer.write(' ');
    }
    // Anything else: dropped. See the docstring.
  }
  return buffer.toString();
}

/// A left label and a right value on one line, dot-free and column-exact.
String twoColumn(String left, String right, int columns) {
  final l = asciiForPrinter(left);
  final r = asciiForPrinter(right);
  if (l.length + r.length + 1 > columns) {
    // Never wrap a money value onto its own line where it could be read as
    // belonging to the next label. Truncate the LABEL; the number is the part
    // that must survive intact.
    final room = columns - r.length - 1;
    if (room <= 0) return r.padLeft(columns).substring(0, columns);
    return '${l.substring(0, room)} $r';
  }
  return l + ' ' * (columns - l.length - r.length) + r;
}

class EscPosDocument {
  EscPosDocument(this.width);
  final PaperWidth width;
  final List<int> _bytes = [];

  int get columns => width.columns;

  void raw(List<int> codes) => _bytes.addAll(codes);

  void line([String text = '']) {
    _bytes.addAll(latin1.encode(asciiForPrinter(text)));
    _bytes.add(0x0A);
  }

  void centred(String text) {
    raw(_Esc.alignCentre);
    line(text);
    raw(_Esc.alignLeft);
  }

  void bold(String text) {
    raw(_Esc.boldOn);
    line(text);
    raw(_Esc.boldOff);
  }

  void rule() => line('-' * columns);

  void pair(String left, String right) => line(twoColumn(left, right, columns));

  List<int> close() {
    raw(_Esc.feedAndCut);
    return List.unmodifiable(_bytes);
  }
}

/// The parchi, rendered for a printer of the given width.
///
/// Field order follows the plain-text slip the server already composes, so the
/// printed copy and the shared copy say the same things in the same sequence —
/// a farmer comparing the two is looking at one document.
List<int> renderSlip(Map<String, dynamic> slip, {PaperWidth width = PaperWidth.mm80}) {
  final doc = EscPosDocument(width);
  String get(String key) => (slip[key] ?? '').toString();

  doc.raw(_Esc.init);
  doc.raw(_Esc.alignCentre);
  doc.raw(_Esc.doubleHeight);
  doc.raw(_Esc.boldOn);
  doc.line(get('organization_name'));
  doc.raw(_Esc.boldOff);
  doc.raw(_Esc.normalSize);
  doc.line(get('center_name'));
  doc.raw(_Esc.alignLeft);
  doc.rule();

  doc.bold('SLIP ${get('slip_number')}');
  doc.pair('Date', get('collected_at').split('T').first);
  doc.pair('Shift', get('session_label'));
  final farmer = [get('supplier_code'), get('supplier_name')].where((s) => s.isNotEmpty).join(' ');
  doc.pair('Farmer', farmer);
  doc.pair('Milk', get('milk_type_custom').isNotEmpty ? get('milk_type_custom') : get('milk_type'));
  doc.rule();

  doc.pair('Quantity', '${get('quantity')} ${get('weight_unit')}');
  doc.pair('Fat %', get('fat'));
  doc.pair('SNF %', get('snf'));
  if (get('clr').isNotEmpty) doc.pair('CLR', get('clr'));
  doc.rule();

  final currency = get('currency');
  final rate = get('unit_price');
  if (rate.isNotEmpty) doc.pair('Rate', '$currency $rate'.trim());
  final amount = get('gross_amount');
  if (amount.isNotEmpty) {
    doc.raw(_Esc.boldOn);
    doc.pair('AMOUNT', '$currency $amount'.trim());
    doc.raw(_Esc.boldOff);
  }
  if (get('pricing_status') == 'PENDING') {
    doc.line('Rate pending - amount to follow');
  }
  doc.rule();

  doc.pair('Operator', get('operator_name'));
  doc.centred(get('decision'));
  return doc.close();
}
