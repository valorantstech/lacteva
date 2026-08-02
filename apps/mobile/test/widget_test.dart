import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/main.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/centers.dart';
import 'package:lacteva_mobile/src/collection_wizard.dart';
import 'package:lacteva_mobile/src/suppliers.dart';
import 'package:qr_flutter/qr_flutter.dart';

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

  testWidgets('readiness screen shows status and checks', (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: ReadinessScreen(client: _ReadinessFake(), centerId: 'c1')),
    );
    await tester.pumpAndSettle();
    expect(find.text('WARNING'), findsOneWidget);
    expect(find.text('1 of 2 checks passing'), findsOneWidget);
    expect(find.text('device.printer'), findsOneWidget);
  });

  testWidgets('supplier detail renders QR and status actions', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: SupplierDetailScreen(client: _SupplierFake(), supplierId: 'c1'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Amina Njoroge'), findsOneWidget);
    expect(find.text('S-AB12CD'), findsWidgets);
    expect(find.text('Activate'), findsOneWidget);
    expect(find.byType(QrImageView), findsOneWidget);
  });

  testWidgets('collection wizard starts at supplier step', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: CollectionWizardScreen(client: _WizardFake(), sessionId: 's1'),
      ),
    );
    expect(find.text('Collection — step 1 of 6'), findsOneWidget);
    expect(find.text('Supplier code'), findsOneWidget);
    expect(find.text('Identify supplier'), findsOneWidget);
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

class _ReadinessFake extends ApiClient {
  @override
  Future<ReadinessResultView> readiness(String centerId) async =>
      ReadinessResultView(status: 'WARNING', checks: [
        ReadinessCheckView(
            rule: 'center.active',
            severity: 'blocking',
            passed: true,
            detail: 'center status is active'),
        ReadinessCheckView(
            rule: 'device.printer',
            severity: 'warning',
            passed: false,
            detail: '0 usable printer(s) of 0 active'),
      ]);
}



class _SupplierFake extends ApiClient {
  @override
  Future<SupplierDetailResult> supplierDetail(String id) async =>
      SupplierDetailResult(
        supplier: SupplierSummary(
          id: id,
          code: 'S-AB12CD',
          status: 'draft',
          fullName: 'Amina Njoroge',
          phone: '+254700000001',
        ),
        village: 'Kilima',
        centerIds: const ['c1'],
        qrPayload: 'LCT1.abc.def',
      );
}

class _WizardFake extends ApiClient {}
