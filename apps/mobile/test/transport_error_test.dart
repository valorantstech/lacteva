/// Transport failure must never leave an operator staring at an eternal
/// spinner (P0-PRODUCT-008 D-1, fixed in P0-PRODUCT-009).
///
/// Before the fix, every operator screen's `_load` caught only
/// `ApiException`: a `SocketException` — the ordinary condition at a
/// collection centre in a dead spot — escaped as an unhandled async error,
/// the spinner spun forever, and pull-to-refresh rethrew silently. What is
/// pinned here is the CONTRACT, on a representative screen of each shape:
/// a dead network produces a visible, actionable message, and the same
/// screen recovers on the next attempt once the network is back.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/centers.dart';

/// A network that is down until told otherwise.
class _FlakyClient extends ApiClient {
  bool offline = true;

  @override
  Future<CenterPage> listCenters({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) async {
    if (offline) throw const SocketException('network is unreachable');
    return CenterPage(items: const [], total: 0);
  }
}

void main() {
  testWidgets('a dead network shows a message, not an eternal spinner', (
    tester,
  ) async {
    final client = _FlakyClient();
    await tester.pumpWidget(MaterialApp(home: CentersListScreen(client: client)));
    await tester.pumpAndSettle();

    // The defect: page == null && error == null kept the spinner forever.
    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.text('Could not reach the platform'), findsOneWidget);
  });

  testWidgets('the same screen recovers once the network is back', (
    tester,
  ) async {
    final client = _FlakyClient();
    await tester.pumpWidget(MaterialApp(home: CentersListScreen(client: client)));
    await tester.pumpAndSettle();
    expect(find.text('Could not reach the platform'), findsOneWidget);

    // Signal returns; the operator retries from the screen itself (search
    // submit reruns the load — same path as pull-to-refresh).
    client.offline = false;
    await tester.enterText(find.byType(TextField).first, '');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();

    expect(find.text('Could not reach the platform'), findsNothing);
    expect(find.text('No centers match.'), findsOneWidget);
  });
}
