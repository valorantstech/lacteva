/// End-of-shift session close (P1-MOBILE-COUNTER-001; audit D-12).
///
/// The platform's `POST /collection-sessions/{id}/close` existed with no
/// caller on ANY client — end-of-shift discipline was impossible. What is
/// pinned on the new centre-detail action:
///   1. no open session → the honest snackbar, nothing sent;
///   2. an open session → a confirm naming the shift; CANCEL closes nothing;
///   3. confirm closes exactly that session, via the platform — whose refusal
///      would render verbatim (the backend stays authoritative; the dialog is
///      a pause, not a boundary).
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/centers.dart';

class _Fake extends ApiClient {
  _Fake({this.openSessions = const []});

  final List<Map<String, dynamic>> openSessions;
  final List<String> closed = [];

  @override
  Future<CenterDetail> centerDetail(String id) async => CenterDetail.fromJson({
    'center': {
      'id': id,
      'branch_id': 'b1',
      'name': 'Village Centre',
      'code': 'VC-1',
      'status': 'active',
      'timezone': null,
    },
    'settings': {},
    'operating_windows': [],
    'calendar': [],
  });

  @override
  Future<List<Map<String, dynamic>>> listOpenSessions(String centerId) async =>
      openSessions;

  @override
  Future<Map<String, dynamic>> closeCollectionSession(String sessionId) async {
    closed.add(sessionId);
    return {'id': sessionId, 'status': 'closed'};
  }
}

Future<void> _pump(WidgetTester tester, _Fake client) async {
  await tester.pumpWidget(
    MaterialApp(
      home: CenterDetailScreen(client: client, centerId: 'c1'),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('no open session: the honest snackbar, nothing sent', (
    tester,
  ) async {
    final client = _Fake();
    await _pump(tester, client);

    await tester.tap(find.byTooltip('Close session'));
    await tester.pumpAndSettle();
    expect(find.text('No open session at this centre'), findsOneWidget);
    expect(client.closed, isEmpty);
  });

  testWidgets('the confirm names the shift; cancel closes nothing', (
    tester,
  ) async {
    final client = _Fake(
      openSessions: [
        {'id': 'ses-1', 'label': 'morning'},
      ],
    );
    await _pump(tester, client);

    await tester.tap(find.byTooltip('Close session'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Closing "morning" ends this shift'), findsOneWidget);

    await tester.tap(find.text('Keep it open'));
    await tester.pumpAndSettle();
    expect(client.closed, isEmpty);
  });

  testWidgets('confirm closes exactly that session via the platform', (
    tester,
  ) async {
    final client = _Fake(
      openSessions: [
        {'id': 'ses-1', 'label': 'morning'},
      ],
    );
    await _pump(tester, client);

    await tester.tap(find.byTooltip('Close session'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Close session').last);
    await tester.pumpAndSettle();

    expect(client.closed, ['ses-1']);
    expect(find.text('Session closed'), findsOneWidget);
  });
}
