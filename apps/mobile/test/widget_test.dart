import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/main.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/centers.dart';

class _FakeClient extends ApiClient {
  @override
  Future<List<BranchSummary>> listBranches() async =>
      [BranchSummary(id: 'b1', name: 'Kilima Hill', code: 'KH')];
}

void main() {
  testWidgets('app starts on the login screen', (tester) async {
    await tester.pumpWidget(const LactevaApp());
    expect(find.text('Lacteva — Sign in'), findsOneWidget);
    expect(find.text('Sign in'), findsWidgets);
  });

  testWidgets('login form validates required fields', (tester) async {
    await tester.pumpWidget(MaterialApp(home: LoginScreen(client: ApiClient())));
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.pump();
    expect(find.text('Enter your email'), findsOneWidget);
    expect(find.text('Enter your password'), findsOneWidget);
  });

  testWidgets('center form validates and loads branches', (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: CenterFormScreen(client: _FakeClient())),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pump();
    expect(find.text('Name needs at least 2 characters'), findsOneWidget);
    expect(find.text('Code is required'), findsOneWidget);
    // Branch dropdown was populated by the fake client.
    expect(find.text('KH — Kilima Hill'), findsOneWidget);
  });

  testWidgets('edit form shows timezone instead of code', (tester) async {
    final center = CenterSummary(
      id: 'c1',
      branchId: 'b1',
      name: 'Kilima Hill Center',
      code: 'KH-C1',
      status: 'inactive',
      timezone: 'UTC',
    );
    await tester.pumpWidget(
      MaterialApp(home: CenterFormScreen(client: _FakeClient(), center: center)),
    );
    await tester.pumpAndSettle();
    expect(find.text('Edit KH-C1'), findsOneWidget);
    expect(find.text('Timezone'), findsOneWidget);
    expect(find.text('Branch'), findsNothing);
  });
}
