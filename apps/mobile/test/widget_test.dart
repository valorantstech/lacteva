import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/main.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/centers.dart';
import 'package:lacteva_mobile/src/collection_wizard.dart';
import 'package:lacteva_mobile/src/pricing_matrices.dart';
import 'package:lacteva_mobile/src/pricing_resolution.dart';
import 'package:lacteva_mobile/src/rate_cards.dart';
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

  testWidgets('rate card form validates required fields', (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: RateCardFormScreen(client: ApiClient())),
    );
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Currency (ISO 4217)'), 'KESH');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pump();
    expect(find.text('Name needs at least 2 characters'), findsOneWidget);
    expect(find.text('Currency must be 3 letters'), findsOneWidget);
    expect(find.text('Enter a date as YYYY-MM-DD'), findsOneWidget);
  });

  testWidgets('rate card list shows status chips and effective range',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: RateCardsListScreen(client: _RateCardFake())),
    );
    await tester.pumpAndSettle();
    expect(find.text('Standard Milk Rates'), findsOneWidget);
    expect(find.text('published'), findsOneWidget);
    expect(find.textContaining('2026-09-01 → open'), findsOneWidget);
  });

  testWidgets('draft rate card detail offers submit and archive',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: RateCardDetailScreen(client: _RateCardFake(), cardId: 'rc-2'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Submit for review'), findsOneWidget);
    expect(find.text('Archive'), findsOneWidget);
    expect(find.text('Publish'), findsNothing);
    expect(find.textContaining('Increment-002'), findsOneWidget);
  });

  testWidgets('published rate card detail offers new version only',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: RateCardDetailScreen(client: _RateCardFake(), cardId: 'rc-1'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('New version'), findsOneWidget);
    expect(find.text('Submit for review'), findsNothing);
    expect(find.text('Products: RAW-COW-MILK'), findsOneWidget);
  });

  testWidgets('matrix list shows bands and dimension', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: MatrixListScreen(client: _MatrixFake(), rateCardId: 'card-1'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Cow Milk FAT Bands'), findsOneWidget);
    expect(find.textContaining('FAT · 2 band(s)'), findsOneWidget);
  });

  testWidgets('editable matrix detail offers the row editor', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: MatrixDetailScreen(client: _MatrixFake(), matrixId: 'm-draft'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('[3.0 – 4.0)'), findsOneWidget);
    expect(find.text('Add band'), findsWidgets);
    expect(find.textContaining('Continuity gaps'), findsOneWidget);
  });

  testWidgets('locked matrix detail is read-only', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: MatrixDetailScreen(client: _MatrixFake(), matrixId: 'm-active'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Add band'), findsNothing);
    expect(find.textContaining('Read-only'), findsOneWidget);
  });

  testWidgets('matrix form validates and loads dimensions', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: MatrixFormScreen(client: _MatrixFake(), rateCardId: 'card-1'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Create'));
    await tester.pump();
    expect(find.text('Name needs at least 2 characters'), findsOneWidget);
    expect(find.text('Product code is required'), findsOneWidget);
    expect(find.text('Pick a dimension'), findsOneWidget);
  });

  testWidgets('resolution screen validates inputs', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ResolutionTestScreen(client: _ResolveFake(), centerId: 'c1'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Resolve'));
    await tester.pump();
    expect(find.text('Product code is required'), findsOneWidget);
    expect(find.text('Pick a dimension'), findsOneWidget);
    expect(find.text('Enter a numeric reading'), findsOneWidget);
  });

  testWidgets('resolution screen shows a match', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ResolutionTestScreen(client: _ResolveFake(), centerId: 'c1'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Product code'), 'RAW-COW-MILK');
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('FAT — Fat').last);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Reading value (e.g. 4.2)'), '4.2');
    await tester.tap(find.widgetWithText(FilledButton, 'Resolve'));
    await tester.pumpAndSettle();
    expect(find.text('Rate card: MILK-STD v1'), findsOneWidget);
    expect(find.text('Unit price: 45 KES'), findsOneWidget);
    expect(find.text('Calculate gross amount'), findsOneWidget);
  });

  testWidgets('calculator computes gross with trace after resolution',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ResolutionTestScreen(client: _ResolveFake(), centerId: 'c1'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Product code'), 'RAW-COW-MILK');
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('FAT — Fat').last);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Reading value (e.g. 4.2)'), '4.2');
    await tester.tap(find.widgetWithText(FilledButton, 'Resolve'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextField, 'Quantity (kg)'), '125.5');
    await tester.tap(find.text('Calculate'));
    await tester.pumpAndSettle();
    expect(find.text('Gross: 5647.50 KES'), findsOneWidget);
    expect(find.textContaining('HALF_UP'), findsWidgets);
    expect(find.text('Trace'), findsOneWidget);
    expect(find.textContaining('multiply:'), findsOneWidget);
  });

  testWidgets('resolution screen shows structured failure', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ResolutionTestScreen(
            client: _ResolveFake(failStage: 'band'), centerId: 'c1'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Product code'), 'RAW-COW-MILK');
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('FAT — Fat').last);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Reading value (e.g. 4.2)'), '9.9');
    await tester.tap(find.widgetWithText(FilledButton, 'Resolve'));
    await tester.pumpAndSettle();
    expect(find.text('No resolution (failed at: band)'), findsOneWidget);
    expect(find.textContaining('no band contains'), findsOneWidget);
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

class _MatrixFake extends ApiClient {
  static final _summary = MatrixSummary(
    id: 'm-draft',
    rateCardCode: 'MILK-STD',
    name: 'Cow Milk FAT Bands',
    productCode: 'RAW-COW-MILK',
    productName: 'Raw Cow Milk',
    dimensionCode: 'FAT',
    status: 'draft',
    version: 1,
    rowCount: 2,
  );

  static final _rows = [
    MatrixRowView(
        id: 'r1', fromValue: 3.0, toValue: 4.0, unitPrice: 40.0, active: true),
    MatrixRowView(
        id: 'r2', fromValue: 5.0, toValue: 6.0, unitPrice: 50.0, active: true),
  ];

  @override
  Future<MatrixPageResult> listMatrices({
    String query = '',
    String rateCardId = '',
    int limit = 20,
    int offset = 0,
  }) async =>
      MatrixPageResult(items: [_summary], total: 1);

  @override
  Future<MatrixDetailResult> matrixDetail(String id) async =>
      MatrixDetailResult(
        matrix: id == 'm-draft'
            ? _summary
            : MatrixSummary(
                id: id,
                rateCardCode: 'MILK-STD',
                name: 'Published Bands',
                productCode: 'RAW-COW-MILK',
                productName: '',
                dimensionCode: 'FAT',
                status: 'active',
                version: 1,
                rowCount: 2,
              ),
        dimensionLabel: 'FAT (%)',
        rows: _rows,
        gaps: const [
          {'from_value': 4.0, 'to_value': 5.0}
        ],
        editable: id == 'm-draft',
      );

  @override
  Future<List<DimensionSummary>> listQualityDimensions() async => [
        DimensionSummary(code: 'FAT', name: 'Fat', unit: '%', active: true),
        DimensionSummary(
            code: 'SNF', name: 'Solids-Not-Fat', unit: '%', active: true),
      ];
}

class _ResolveFake extends ApiClient {
  _ResolveFake({this.failStage});

  final String? failStage;

  @override
  Future<List<DimensionSummary>> listQualityDimensions() async => [
        DimensionSummary(code: 'FAT', name: 'Fat', unit: '%', active: true),
      ];

  @override
  Future<ResolutionResultView> resolvePricing({
    required String centerId,
    required String productCode,
    required String transactionDate,
    required String dimensionCode,
    required double value,
  }) async {
    if (failStage != null) {
      throw ApiException(422, 'No applicable pricing was found.', extra: {
        'stage': failStage,
        'reason': 'no band contains the reading $value',
      });
    }
    return ResolutionResultView(
      rowId: 'row-1',
      rateCardCode: 'MILK-STD',
      rateCardVersion: 1,
      matrixName: 'Cow Milk FAT Bands',
      rangeFrom: 4.0,
      rangeTo: 5.0,
      priceAmount: '45',
      currency: 'KES',
      readingValue: value,
      readingUnit: '%',
    );
  }

  @override
  Future<CalculationResultView> calculatePricing({
    required String rowId,
    required double quantity,
    required String transactionDate,
    String quantityUnit = 'kg',
    String? roundingPolicy,
  }) async =>
      CalculationResultView(
        grossAmount: '5647.50',
        unitPrice: '45',
        currency: 'KES',
        quantityValue: quantity,
        quantityUnit: quantityUnit,
        roundingPolicy: 'HALF_UP',
        calculatorVersion: '1.0.0',
        trace: [
          CalculationTraceStepView(
              operation: 'multiply',
              detail: 'gross = unit price x quantity',
              values: const {'raw_amount': '5647.500'}),
          CalculationTraceStepView(
              operation: 'round',
              detail: 'HALF_UP to 2 decimal place(s)',
              values: const {'rounded_amount': '5647.50'}),
        ],
      );
}

class _RateCardFake extends ApiClient {
  static final _published = RateCardSummary(
    id: 'rc-1',
    code: 'MILK-STD',
    name: 'Standard Milk Rates',
    description: '',
    currency: 'KES',
    effectiveFrom: '2026-09-01',
    effectiveUntil: null,
    status: 'published',
    version: 1,
  );

  static final _draft = RateCardSummary(
    id: 'rc-2',
    code: 'MILK-NEW',
    name: 'Next Season Rates',
    description: 'Season 27/28',
    currency: 'KES',
    effectiveFrom: '2027-09-01',
    effectiveUntil: '2028-08-31',
    status: 'draft',
    version: 1,
  );

  @override
  Future<RateCardPageResult> listRateCards({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) async =>
      RateCardPageResult(items: [_published], total: 1);

  @override
  Future<RateCardDetailResult> rateCardDetail(String id) async =>
      RateCardDetailResult(
        card: id == 'rc-1' ? _published : _draft,
        centerIds: const ['c1'],
        productCodes: id == 'rc-1' ? const ['RAW-COW-MILK'] : const [],
      );
}
