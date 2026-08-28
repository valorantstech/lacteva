/// The walker draws the artwork, not something like it (LACTEVA-BRAND-004).
///
/// The wordmark reaches Flutter as path DATA rather than as generated
/// `..cubicTo` chains, so between the traced outlines and the pixels there is
/// now a parser. A parser is a place a logo can go quietly wrong — a dropped
/// command, a mis-scaled point, a hole filled in — and none of those would
/// throw. They would just draw a slightly different logo.
///
/// So this checks the drawing, not the parsing: where the ink is, where it is
/// not, and that the one hole in the artwork is still a hole.
library;


import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/brand/mark.g.dart';
import 'package:lacteva_mobile/src/brand/path_data.dart';

void main() {
  group('the walker', () {
    test('draws every traced layer without complaint', () {
      for (final data in [
        kWordmarkNavyData,
        kWordmarkGreenData,
        kWordmarkRuleData,
        kWordmarkTaglineData,
      ]) {
        expect(lactevaPathData(data).getBounds().isEmpty, isFalse);
      }
    });

    test('lands the caps where the generator says they are', () {
      // Skia's bounds are conservative — they take in the control points, so
      // they can sit slightly outside the true outline. A couple of units on
      // a 646-wide artwork is that, and nothing else.
      final bounds = lactevaPathData(
        '$kWordmarkNavyData$kWordmarkGreenData',
      ).getBounds();
      expect(bounds.left, closeTo(kWordmarkCapsBounds.left, 2));
      expect(bounds.top, closeTo(kWordmarkCapsBounds.top, 2));
      expect(bounds.right, closeTo(kWordmarkCapsBounds.right, 2));
      expect(bounds.bottom, closeTo(kWordmarkCapsBounds.bottom, 2));
    });

    test('puts ink in the L and leaves the paper alone', () {
      final navy = lactevaPathData(kWordmarkNavyData);
      // Inside the L's stem.
      expect(navy.contains(const Offset(33, 60)), isTrue);
      // Above the cap line, where nothing is drawn.
      expect(navy.contains(const Offset(33, 10)), isFalse);
      // The gap between LACTE and the V, which belongs to neither layer.
      expect(navy.contains(const Offset(450, 70)), isFalse);
    });

    test('keeps the drop in the final A a HOLE', () {
      // The owner's A carries a knockout drop. If the walker got the winding
      // wrong — or a fill rule flattened it — the drop would fill in and
      // nothing would throw; the logo would simply be wrong on every screen
      // that draws it.
      final green = lactevaPathData(kWordmarkGreenData);
      expect(green.contains(const Offset(590, 95)), isFalse,
          reason: 'the drop in the final A must not be filled');
      // ...while the A's own diagonal, just outside the drop, is ink.
      expect(green.contains(const Offset(575, 100)), isTrue);
    });

    test('scales and crops about the origin it is given', () {
      final full = lactevaPathData(kWordmarkNavyData).getBounds();
      final cropped = lactevaPathData(
        kWordmarkNavyData,
        scale: 2,
        origin: kWordmarkCapsBounds.topLeft,
      ).getBounds();
      expect(cropped.left, closeTo((full.left - kWordmarkCapsBounds.left) * 2, 0.01));
      expect(cropped.width, closeTo(full.width * 2, 0.01));
    });

    test('refuses a command it does not know', () {
      // A renderer that skips what it cannot read draws a silently wrong
      // logo, which is worse than one that fails loudly.
      expect(
        () => lactevaPathData('M0 0L5 5Q9 9 10 10Z'),
        throwsA(isA<FormatException>()),
      );
      expect(() => lactevaPathData('L5 5'), throwsA(isA<FormatException>()));
    });
  });

  group('the can and the drop still agree with their bounds', () {
    test('the generated Rects describe the generated Paths', () {
      for (final (path, bounds) in [
        (lactevaCanPath(1), kCanBounds),
        (lactevaDropPath(1), kMarkBounds),
      ]) {
        final drawn = path.getBounds();
        expect(drawn.left, closeTo(bounds.left, 1));
        expect(drawn.top, closeTo(bounds.top, 1));
        expect(drawn.width, closeTo(bounds.width, 1));
        expect(drawn.height, closeTo(bounds.height, 1));
      }
    });
  });
}
