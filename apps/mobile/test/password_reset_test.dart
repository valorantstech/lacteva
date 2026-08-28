/// Forgotten password on the handset (LACTEVA-ADMIN-003).
///
/// A locked-out operator at 5 a.m. was a phone call to somebody who might not
/// answer: the backend flow existed, rate-limited and enumeration-safe, and
/// neither login surface offered it.
///
/// What is pinned:
///   1. step 1 reaches the platform's own endpoint and moves to step 2;
///   2. step 2 spends the code and hands the reason back to the sign-in
///      screen, through the `notice` slot it already has;
///   3. a transport failure SAYS SO — R-1's whole point, and the reason the
///      structural guard in `save_transport_error_test.dart` exists;
///   4. a rate limit is named honestly, because it is about the IP and
///      reveals nothing about any account;
///   5. and the enumeration defence survives the UI: the platform answers 202
///      for an address it has never seen exactly as for one it knows, so this
///      screen must look identical either way.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/brand/auth_lockup.dart';
import 'package:lacteva_mobile/src/brand/mark.dart';
import 'package:lacteva_mobile/src/brand/wordmark.dart';
import 'package:lacteva_mobile/src/password_reset.dart';

class _Fake extends ApiClient {
  _Fake({this.requestError, this.confirmError});

  final Object? requestError;
  final Object? confirmError;
  final List<String> asked = [];
  final List<List<String>> confirmed = [];

  @override
  Future<void> requestPasswordReset(String email) async {
    asked.add(email);
    if (requestError != null) throw requestError!;
  }

  @override
  Future<void> confirmPasswordReset(String token, String newPassword) async {
    confirmed.add([token, newPassword]);
    if (confirmError != null) throw confirmError!;
  }
}

/// A distinct key per pump: pumping a second screen of the same type into the
/// same slot would otherwise REUSE the first one's State, and the test would
/// silently be looking at step 2 when it meant to start again at step 1.
Future<void> _pump(WidgetTester tester, _Fake client) async {
  await tester.pumpWidget(
    MaterialApp(home: PasswordResetScreen(key: UniqueKey(), client: client)),
  );
  await tester.pumpAndSettle();
}

/// The field under a given label.
///
/// WO-36 adds a third box to step 2, and `find.byType(TextField).last` used
/// to mean "new password" only because it happened to be last. A positional
/// selector that stops meaning what it meant is the same failure QA-003 and
/// QA-005 chased through the portal; this asks for the field by its name.
Finder _field(String label) =>
    find.ancestor(of: find.text(label), matching: find.byType(TextField));

/// Step 1, all the way to the code field.
Future<void> _ask(WidgetTester tester, String email) async {
  await tester.enterText(find.byType(TextField).first, email);
  await tester.tap(find.text('Send reset code'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('step 1 asks the platform and moves on', (tester) async {
    final client = _Fake();
    await _pump(tester, client);
    await _ask(tester, 'manager@kilima.example');

    expect(client.asked, ['manager@kilima.example']);
    expect(find.text('Reset code'), findsOneWidget);
    expect(find.text('New password'), findsOneWidget);
    // The minimum is stated where it is needed, not discovered on refusal.
    expect(find.text('At least 10 characters.'), findsOneWidget);
  });

  testWidgets('step 1 says the same words whatever the platform found', (
    tester,
  ) async {
    // Both addresses get 202 from the platform; the screen must not tell
    // them apart, or the 202 was for nothing.
    await _pump(tester, _Fake());
    await _ask(tester, 'manager@kilima.example');
    final real = find
        .byType(Text)
        .evaluate()
        .map((e) => (e.widget as Text).data ?? '')
        .map((s) => s.replaceAll('manager@kilima.example', '{email}'))
        .toList();

    await _pump(tester, _Fake());
    await _ask(tester, 'nobody@nowhere.example');
    final fictional = find
        .byType(Text)
        .evaluate()
        .map((e) => (e.widget as Text).data ?? '')
        .map((s) => s.replaceAll('nobody@nowhere.example', '{email}'))
        .toList();

    expect(fictional, real);
    expect(
      real.any((s) => s.contains('If an account exists for {email}')),
      isTrue,
    );
  });

  testWidgets('step 2 spends the code and hands back the reason', (
    tester,
  ) async {
    final client = _Fake();
    String? handedBack;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () async {
              handedBack = await Navigator.of(context).push<String>(
                MaterialPageRoute(
                  builder: (_) => PasswordResetScreen(client: client),
                ),
              );
            },
            child: const Text('open'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    await _ask(tester, 'manager@kilima.example');
    await tester.enterText(_field('Reset code'), 'code-xyz');
    await tester.enterText(_field('New password'), 'correct-horse-battery');
    await tester.enterText(
      _field('Confirm new password'),
      'correct-horse-battery',
    );
    await tester.tap(find.text('Set new password'));
    await tester.pumpAndSettle();

    expect(client.confirmed, [
      ['code-xyz', 'correct-horse-battery'],
    ]);
    // The `notice` slot the LoginScreen already has, carrying WHY.
    expect(handedBack, 'Your password was updated — sign in to continue.');
  });

  group('the two new passwords must agree (WO-36)', () {
    testWidgets('a mismatch blocks the submit and names the problem', (
      tester,
    ) async {
      final client = _Fake();
      await _pump(tester, client);
      await _ask(tester, 'manager@kilima.example');

      await tester.enterText(_field('Reset code'), 'code-xyz');
      await tester.enterText(_field('New password'), 'correct-horse-battery');
      await tester.enterText(_field('Confirm new password'), 'correct-horse');
      await tester.tap(find.text('Set new password'));
      await tester.pumpAndSettle();

      // The platform is never asked. A typo in a password nobody can read
      // back is the one mistake this screen can catch before it costs
      // somebody their only way in.
      expect(client.confirmed, isEmpty);
      // ...and it says what is wrong, at the field that is wrong.
      expect(
        find.text('Those two passwords do not match.'),
        findsOneWidget,
      );
    });

    testWidgets('correcting the confirmation lets it through', (tester) async {
      final client = _Fake();
      await _pump(tester, client);
      await _ask(tester, 'manager@kilima.example');

      await tester.enterText(_field('Reset code'), 'code-xyz');
      await tester.enterText(_field('New password'), 'correct-horse-battery');
      await tester.enterText(_field('Confirm new password'), 'wrong');
      await tester.tap(find.text('Set new password'));
      await tester.pumpAndSettle();
      expect(client.confirmed, isEmpty);

      // Typing again clears the complaint rather than leaving it under a
      // field the person has already fixed.
      await tester.enterText(
        _field('Confirm new password'),
        'correct-horse-battery',
      );
      await tester.pumpAndSettle();
      expect(find.text('Those two passwords do not match.'), findsNothing);

      await tester.tap(find.text('Set new password'));
      await tester.pumpAndSettle();
      expect(client.confirmed, [
        ['code-xyz', 'correct-horse-battery'],
      ]);
    });

    testWidgets('the platform still receives exactly what it always did', (
      tester,
    ) async {
      // The confirmation is a client-side courtesy. The contract is two
      // arguments, and this screen must not have quietly grown a third.
      final client = _Fake();
      await _pump(tester, client);
      await _ask(tester, 'manager@kilima.example');
      await tester.enterText(_field('Reset code'), 'code-xyz');
      await tester.enterText(_field('New password'), 'a-long-enough-secret');
      await tester.enterText(
        _field('Confirm new password'),
        'a-long-enough-secret',
      );
      await tester.tap(find.text('Set new password'));
      await tester.pumpAndSettle();
      expect(client.confirmed.single, hasLength(2));
      expect(client.confirmed.single, ['code-xyz', 'a-long-enough-secret']);
    });

    testWidgets('the ten-character rule is still on the screen', (
      tester,
    ) async {
      final client = _Fake();
      await _pump(tester, client);
      await _ask(tester, 'manager@kilima.example');
      expect(find.text('At least 10 characters.'), findsOneWidget);
    });
  });

  group('it wears the same face as sign-in (WO-36)', () {
    testWidgets('the lockup is on the reset screen too', (tester) async {
      final client = _Fake();
      await _pump(tester, client);
      // The can, the traced letterforms and the tagline — the same widget
      // sign-in uses, not a second arrangement of the same parts.
      expect(find.byType(AuthLockup), findsOneWidget);
      expect(find.byType(LactevaCanMark), findsOneWidget);
      expect(find.byType(LactevaWordmark), findsOneWidget);
    });

    testWidgets('and it survives into step 2', (tester) async {
      final client = _Fake();
      await _pump(tester, client);
      await _ask(tester, 'manager@kilima.example');
      expect(find.byType(AuthLockup), findsOneWidget);
    });
  });

  testWidgets('a transport failure says so instead of sitting there', (
    tester,
  ) async {
    // R-1: a button that un-busies with no message reads as success.
    final client = _Fake(
      requestError: const SocketException('network is unreachable'),
    );
    await _pump(tester, client);
    await _ask(tester, 'manager@kilima.example');

    expect(find.text('Could not reach the platform'), findsOneWidget);
    // Still on step 1, with the form to retry from.
    expect(find.text('Reset code'), findsNothing);
  });

  testWidgets('a rate limit is named, and nothing is claimed about the account', (
    tester,
  ) async {
    final client = _Fake(requestError: ApiException(429, 'slow down'));
    await _pump(tester, client);
    await _ask(tester, 'manager@kilima.example');

    expect(find.text('Too many attempts — try again later.'), findsOneWidget);
    expect(find.text('Reset code'), findsNothing);
  });

  testWidgets('the platform reason for a stale code is shown verbatim', (
    tester,
  ) async {
    final client = _Fake(
      confirmError: ApiException(400, 'That reset code has expired.'),
    );
    await _pump(tester, client);
    await _ask(tester, 'manager@kilima.example');

    // Named, not counted: WO-36 put a third box on this step, and `.last`
    // used to mean "new password" only because it happened to be last.
    await tester.enterText(_field('Reset code'), 'stale');
    await tester.enterText(_field('New password'), 'correct-horse-battery');
    await tester.enterText(
      _field('Confirm new password'),
      'correct-horse-battery',
    );
    await tester.tap(find.text('Set new password'));
    await tester.pumpAndSettle();

    expect(find.text('That reset code has expired.'), findsOneWidget);
  });
}
