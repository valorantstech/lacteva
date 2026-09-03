/// The address a distributed build carries (WO-63 · LACTEVA-DEPLOY-004).
///
/// `LACTEVA_API_URL` is a compile-time constant. That is the whole reason
/// `api.lacteva.com` exists as a name of its own: changing this value means
/// building, signing and shipping a release, and every handset already in the
/// field keeps calling whatever it was built with until somebody updates it.
/// A DNS record can be repointed in a minute; an installed APK cannot.
///
/// The name it replaced, `dev.phoenixsoft.in`, was retired on 2026-09-03 and
/// every install built against it lost its server that day — which is the
/// clearest possible statement of why this constant deserves a name of its
/// own that can be repointed in DNS.
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

  test('the retired address is documented as retired, with its cost', () {
    // `dev.phoenixsoft.in` was retired on 2026-09-03. The README is where
    // somebody looks before building, so it has to say both that the name is
    // gone AND what that did to the handsets built against it — a name simply
    // deleted from the docs reads as a name that never mattered.
    final readme = _find('README.md').readAsStringSync();
    expect(readme.contains('dev.phoenixsoft.in'), isTrue,
        reason: 'the retirement must be recorded, not erased');
    expect(readme.contains('retired'), isTrue);
    expect(
      readme.contains('reinstalled') || readme.contains('lost its server'),
      isTrue,
      reason: 'the consequence for installed handsets has to be stated where '
          'the person doing the next build will read it',
    );
  });
}
