/// The address a distributed build carries (WO-63 · LACTEVA-DEPLOY-004).
///
/// `LACTEVA_API_URL` is a compile-time constant. That is the whole reason
/// `api.lacteva.com` exists as a name of its own: changing this value means
/// building, signing and shipping a release, and every handset already in the
/// field keeps calling whatever it was built with until somebody updates it.
/// A DNS record can be repointed in a minute; an installed APK cannot.
///
/// So two things are pinned here, and neither of them is the value itself —
/// a build passes it in, and a test cannot see a `--dart-define` that was not
/// given to it. What can be checked is that the default is still the local
/// one (a build that forgets the define must fail loudly against localhost
/// rather than silently reaching production), and that the README states the
/// address a release is supposed to be built against, which is the only place
/// the person doing it will look.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/main.dart' as app;

File _find(String relative) {
  for (final base in [Directory.current, Directory.current.parent]) {
    final candidate = File('${base.path}/$relative');
    if (candidate.existsSync()) return candidate;
  }
  fail('could not find $relative from ${Directory.current.path}');
}

void main() {
  test('an undefined API address stays local, and never a live platform', () {
    // If this ever defaults to a real host, a build that forgot the define
    // ships pointing at production and nobody finds out until it works.
    expect(app.apiUrl, 'http://localhost:8000');
  });

  test('the README names the address a release is built against', () {
    final readme = _find('README.md').readAsStringSync();
    expect(
      readme.contains('--dart-define=LACTEVA_API_URL=https://api.lacteva.com'),
      isTrue,
      reason: 'the release build command must state the API address, or the '
          'next person builds against whatever they remember',
    );
  });

  test('the old address is documented as kept, not retired', () {
    // Every demo handset in the field was built against it. Saying so where
    // the build command lives is what stops somebody "tidying it up".
    final readme = _find('README.md').readAsStringSync();
    expect(readme.contains('dev.phoenixsoft.in'), isTrue);
  });
}
