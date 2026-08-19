/// Every catalog key has a caller (P1-LOCALE-I18N-001).
///
/// The "catalog without callers" defect has now been found THREE times in this
/// codebase: keys were written in all three languages, the screen retyped the
/// English beside them, and a Hindi operator read English from a screen whose
/// translation had existed for months. Reviews did not catch it because both
/// halves look correct in isolation.
///
/// So the property is executable: a key that exists must be looked up
/// somewhere in `lib/`. This is the mirror of the parity test — parity proves
/// every key is TRANSLATED, this proves every key is USED. Together they close
/// the loop that a language actually reaches a screen.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/l10n.dart';

/// Keys looked up through a computed expression rather than a literal — the
/// catalog families that exist precisely to map a server CODE to a word. Their
/// call site is `t('status.$code')`, so no literal appears in the source.
const _dynamicFamilies = <String>[
  'status.', // deliveries.dart: t('status.$status')
  'driver.outcome.', // driver.dart: t('driver.outcome.$outcome')
  'slot.', // record screens: t('slot.$slot')
  'milk.', // collection wizard: t('milk.$milkType')
];

void main() {
  test('every catalog key is looked up somewhere in lib/', () {
    final source = Directory('lib')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'))
        .map((f) => f.readAsStringSync())
        .join('\n');

    final orphans = <String>[];
    for (final key in catalogs['en']!.keys) {
      if (_dynamicFamilies.any(key.startsWith)) continue;
      // The literal as it appears in a lookup: t('key') or t("key").
      if (source.contains("'$key'") || source.contains('"$key"')) continue;
      orphans.add(key);
    }

    expect(
      orphans,
      isEmpty,
      reason:
          'These keys are translated but never shown — either wire them to '
          'the screen that retypes their English, or delete them: $orphans',
    );
  });

  test('the dynamic families still resolve for the codes they serve', () {
    // A family is exempt from the caller check above, so its members must be
    // proven reachable here instead — otherwise the exemption becomes a hole.
    const en = 'en';
    for (final code in ['scheduled', 'delivered', 'skipped', 'returned', 'cancelled']) {
      expect(L10n(en).t('status.$code'), isNot('status.$code'));
    }
    for (final code in ['delivered', 'skipped', 'returned', 'cancelled']) {
      expect(L10n(en).t('driver.outcome.$code'), isNot('driver.outcome.$code'));
    }
    for (final code in ['morning', 'evening']) {
      expect(L10n(en).t('slot.$code'), isNot('slot.$code'));
    }
    // The milk types the collection wizard offers.
    for (final code in ['cow', 'buffalo', 'goat', 'mixed']) {
      expect(L10n(en).t('milk.$code'), isNot('milk.$code'));
    }
  });
}
