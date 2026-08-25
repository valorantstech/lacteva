/// A save that fails in transit must SAY SO (P1-PRODUCT-READINESS-001 R-1).
///
/// P0-PRODUCT-009 gave every operator LOAD path a generic transport fallback,
/// which fixed the eternal-spinner class. The SAVE paths are a different
/// shape and were missed: they caught `on ApiException` only, so a
/// `SocketException` — the ordinary condition at a collection centre in a dead
/// spot — was never caught. The `finally` cleared the busy flag, `_error` was
/// never set, and the form simply sat there having done nothing.
///
/// That is a worse failure than a spinner. A spinner is visibly wrong; a
/// button that un-busies with no message reads as success, and a field agent
/// could reasonably walk away believing a farmer had been created.
///
/// Two guards, because they protect different things: the first proves the
/// message reaches the operator on a representative save path, and the second
/// prevents the whole class from coming back anywhere in the app — including
/// in files that do not exist yet.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/suppliers.dart';

class _UnreachableClient extends ApiClient {
  @override
  Future<SupplierSummary> createSupplier({
    required String fullName,
    String phone = '',
    String village = '',
  }) async {
    throw const SocketException('network is unreachable');
  }
}

void main() {
  testWidgets('a save that cannot reach the platform says so', (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: SupplierFormScreen(client: _UnreachableClient())),
    );
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextFormField).first, 'Ramesh Gowda');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    // The defect: no message, and the button back to "Save" as if nothing
    // had happened.
    expect(find.text('Could not reach the platform'), findsOneWidget);
    // And the form is still there to retry with — the entry is not lost.
    expect(find.byType(SupplierFormScreen), findsOneWidget);
  });

  test('no catch anywhere handles ApiException without a transport fallback', () {
    // The structural half. A future screen that catches only `ApiException`
    // reintroduces R-1 silently, because the happy path still works and the
    // failure only appears where there is no signal — which is exactly where
    // nobody is running tests.
    //
    // Three sites are deliberately exempt, each for a stated reason. If one of
    // them changes shape this list is what fails, which is the intent.
    const deliberate = <String>{
      // A nested try that rethrows anything that is not a 404; the ENCLOSING
      // try carries the generic fallback.
      'lib/src/driver.dart',
      // The replay drain classifies transport failure itself, one level up:
      // a transport error must stay RETRYABLE rather than becoming a refusal,
      // and that behaviour is pinned by replay_auth_test.dart.
      'lib/src/offline/offline_client.dart',
    };

    final offenders = <String>[];
    for (final file in Directory('lib').listSync(recursive: true).whereType<File>()) {
      if (!file.path.endsWith('.dart')) continue;
      if (deliberate.contains(file.path)) continue;
      final lines = file.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        if (!lines[i].contains('on ApiException catch')) continue;
        final window = lines.skip(i + 1).take(13).join('\n');
        final hasFallback =
            RegExp(r'\}\s*catch\s*\(').hasMatch(window) || window.contains('on Exception');
        if (!hasFallback) offenders.add('${file.path}:${i + 1}');
      }
    }

    expect(
      offenders,
      isEmpty,
      reason:
          'these catch a platform refusal but not a transport failure, so they '
          'fail silently where there is no signal: $offenders',
    );
  });
}
