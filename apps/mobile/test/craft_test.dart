/// The craft defects (WO-72 Part A · D-23 pins 1, 4, 5, 7, 8, 9).
///
/// Individually trivial, and collectively the reason the dashboard read as
/// "implemented by a college student": `1 farmers served`, `06:00:00 –
/// 19:00:00`, a hero figure with no unit, an empty card, a hole in a grid.
/// Each is pinned here so it cannot return.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/format.dart';
import 'package:lacteva_mobile/src/l10n.dart';

void main() {
  group('ICU plurals (pin 4)', () {
    test('no counted string can render "1 farmers"', () {
      final en = L10n('en');
      expect(en.t('manager.farmersServed', {'count': 1}), '1 farmer served');
      expect(en.t('manager.farmersServed', {'count': 38}), '38 farmers served');
      expect(en.t('manager.farmersServed', {'count': 0}), 'No farmers yet');
      expect(en.t('customer.deliveries', {'count': 1}), '1 delivery');
      expect(en.t('customer.deliveries', {'count': 2}), '2 deliveries');
      expect(en.t('sync.needAttention', {'count': 1}), '1 item needs attention');
      expect(en.t('sync.needAttention', {'count': 3}), '3 items need attention');
      expect(en.t('manager.unpriced', {'count': 1}), '1 collection is waiting for a price');
      expect(en.t('driver.remaining', {'count': 1}), '1 stop remaining');
      expect(en.t('round.customerCount', {'count': 1}), '1 customer');
      expect(en.t('sync.sending', {'count': 1}), 'Sending 1 collection…');
    });

    test('Hindi counts 0 and 1 as one; Arabic has six categories', () {
      expect(pluralCategory(0, 'hi'), 'one');
      expect(pluralCategory(1, 'hi'), 'one');
      expect(pluralCategory(2, 'hi'), 'other');
      expect(pluralCategory(0, 'ar'), 'zero');
      expect(pluralCategory(1, 'ar'), 'one');
      expect(pluralCategory(2, 'ar'), 'two');
      expect(pluralCategory(3, 'ar'), 'few');
      expect(pluralCategory(10, 'ar'), 'few');
      expect(pluralCategory(11, 'ar'), 'many');
      expect(pluralCategory(99, 'ar'), 'many');
      expect(pluralCategory(100, 'ar'), 'other');
      expect(pluralCategory(1, 'en'), 'one');
      expect(pluralCategory(0, 'en'), 'other');
    });

    test('every language renders every counted string for 1 and for many', () {
      final counted = <String>[
        'driver.remaining',
        'customer.deliveries',
        'sync.needAttention',
        'sync.syncingItems',
        'manager.farmersServed',
        'manager.recentShape',
        'manager.unpriced',
        'round.customerCount',
        'sync.sending',
      ];
      for (final language in ['en', 'hi', 'ar']) {
        final l = L10n(language);
        for (final key in counted) {
          for (final n in [0, 1, 2, 5, 11, 38]) {
            final text = l.t(key, {'count': n});
            expect(text, isNot(contains('plural')), reason: '$language $key $n: $text');
            expect(text, isNot(contains('{')), reason: '$language $key $n: $text');
            expect(text, isNot(contains('#')), reason: '$language $key $n: $text');
          }
          // The number itself appears for a count with no special word for it.
          expect(l.t(key, {'count': 38}), contains('38'), reason: '$language $key');
        }
      }
      final hi = L10n('hi');
      expect(hi.t('manager.farmersServed', {'count': 1}), '1 किसान से लिया');
      expect(hi.t('manager.farmersServed', {'count': 38}), '38 किसानों से लिया');
      final ar = L10n('ar');
      expect(ar.t('manager.farmersServed', {'count': 1}), 'خدمة مزارع واحد');
      expect(ar.t('manager.farmersServed', {'count': 5}), 'خدمة 5 مزارعين');
    });

    test('a catalog without a category falls back to other, never to the template', () {
      expect(
        resolvePlurals('{n, plural, one{# item} other{# items}}', {'n': 3}, 'ar'),
        '3 items',
      );
      expect(resolvePlurals('no plural here {n}', {'n': 3}, 'en'), 'no plural here {n}');
    });
  });

  group('human time (pin 5)', () {
    test('seconds never reach a person', () {
      expect(humanTime('06:00:00'), '6 am');
      expect(humanTime('19:00:00'), '7 pm');
      expect(humanTime('12:00:00'), '12 pm');
      expect(humanTime('00:30:00'), '12:30 am');
      expect(humanTime('19:30'), '7:30 pm');
      expect(humanWindow('06:00:00', '19:00:00'), '6 am – 7 pm');
      expect(humanWindow('06:00:00', '19:00:00', language: 'hi'), 'सुबह 6 – शाम 7');
      expect(humanWindow('06:00:00', '19:00:00', language: 'ar'), '6 ص – 7 م');
      // Not a time: shown as sent, never mangled.
      expect(humanTime('soon'), 'soon');
    });

    test('an operating window labels itself for a person', () {
      final window = OperatingWindowView(dayOfWeek: 0, opens: '06:00:00', closes: '19:00:00');
      expect(window.humanLabel(), 'Mon · 6 am – 7 pm');
      expect(window.humanLabel(language: 'hi'), 'Mon · सुबह 6 – शाम 7');
    });

    test('an instant becomes a stamp without seconds or a T', () {
      expect(stamp('2026-09-03T21:44:12.456190+05:30'), '2026-09-03 21:44');
      expect(stamp('2026-09-03 21:44:12'), '2026-09-03 21:44');
      expect(stamp(null), '');
      expect(stamp('yesterday'), 'yesterday');
    });
  });

  test('no raw machine timestamp reaches a label in lib/ (pin 5 audit)', () {
    // The shape that put `2026-09-03 21:44:12` — seconds and all — under a
    // payment, a notification, a receipt and a history row.
    final offenders = <String>[];
    for (final file in Directory('lib/src').listSync(recursive: true).whereType<File>()) {
      if (!file.path.endsWith('.dart') || file.path.contains('/offline/')) continue;
      final lines = file.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        if (lines[i].contains(".replaceFirst('T', ' ').split('.').first")) {
          offenders.add('${file.path}:${i + 1}');
        }
      }
    }
    expect(offenders, isEmpty);
  });
}
