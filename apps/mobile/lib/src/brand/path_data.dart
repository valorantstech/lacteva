/// Walk generated SVG path data into a Flutter `Path` (LACTEVA-BRAND-004).
///
/// **Why this exists.** The owner's LACTEVA letterforms are traced artwork —
/// four layers, some thirteen kilobytes of path data. Emitting them as
/// `..cubicTo` call chains, the way the can and the drop are emitted, comes to
/// roughly sixty kilobytes of generated Dart. Emitting the data and walking it
/// here is smaller, and it puts the thing that needs checking in one testable
/// function instead of spread over a thousand generated call sites.
///
/// **It is deliberately not an SVG parser.** `tools/brand/mark.py` emits
/// exactly four commands — `M`, `L`, `C`, `Z`, all absolute — so those four
/// are what this understands. Anything else throws rather than being skipped:
/// a renderer that quietly ignores a command it does not know draws a
/// SILENTLY WRONG logo, which is worse than one that fails to draw at all.
///
/// Adding `flutter_svg` instead would be a dependency, a licence and a general
/// parser on the launch path of an app that already ships, to read four
/// commands out of a file this repository generates itself.
library;

import 'dart:ui';

/// Parse `data` into a path, scaled by [scale] about the artwork's origin.
///
/// [origin] is subtracted BEFORE scaling, so a caller that wants the caps
/// cropped to their own box passes that box's top-left and gets a path that
/// starts at zero.
Path lactevaPathData(String data, {double scale = 1.0, Offset origin = Offset.zero}) {
  final path = Path();
  final length = data.length;
  var index = 0;
  var started = false;

  double number() {
    // Skip separators. A comma or a space may or may not be there; a minus
    // sign is a separator too when it opens the next number.
    while (index < length) {
      final c = data.codeUnitAt(index);
      if (c == 0x20 || c == 0x2C) {
        index++;
      } else {
        break;
      }
    }
    final start = index;
    if (index < length &&
        (data.codeUnitAt(index) == 0x2D || data.codeUnitAt(index) == 0x2B)) {
      index++;
    }
    while (index < length) {
      final c = data.codeUnitAt(index);
      // digits, the decimal point, and an exponent's own sign
      final isDigit = c >= 0x30 && c <= 0x39;
      if (isDigit || c == 0x2E) {
        index++;
      } else if (c == 0x65 || c == 0x45) {
        index++;
        if (index < length &&
            (data.codeUnitAt(index) == 0x2D || data.codeUnitAt(index) == 0x2B)) {
          index++;
        }
      } else {
        break;
      }
    }
    if (start == index) {
      throw FormatException('expected a number at $index', data, index);
    }
    return double.parse(data.substring(start, index));
  }

  Offset point() {
    final x = number();
    final y = number();
    return Offset((x - origin.dx) * scale, (y - origin.dy) * scale);
  }

  while (index < length) {
    final command = data[index];
    if (command == ' ' || command == ',' || command == '\n') {
      index++;
      continue;
    }
    index++;
    switch (command) {
      case 'M':
        final p = point();
        path.moveTo(p.dx, p.dy);
        started = true;
      case 'L':
        if (!started) {
          throw FormatException('a line before any move', data, index);
        }
        final p = point();
        path.lineTo(p.dx, p.dy);
      case 'C':
        if (!started) {
          throw FormatException('a curve before any move', data, index);
        }
        final c1 = point();
        final c2 = point();
        final end = point();
        path.cubicTo(c1.dx, c1.dy, c2.dx, c2.dy, end.dx, end.dy);
      case 'Z':
        path.close();
      default:
        throw FormatException(
          'unsupported path command "$command" — the generator emits only '
          'M, L, C and Z',
          data,
          index - 1,
        );
    }
  }
  return path;
}

/// The scale that fits [bounds] into a box [height] tall.
double lactevaScaleFor(Rect bounds, double height) => height / bounds.height;
