import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/main.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/offline/store.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/center_summary.dart';
import 'package:lacteva_mobile/src/centers.dart';
import 'package:lacteva_mobile/src/collection_wizard.dart';
import 'package:lacteva_mobile/src/notifications.dart';
import 'package:lacteva_mobile/src/payments.dart';
import 'package:lacteva_mobile/src/pricing_matrices.dart';
import 'package:lacteva_mobile/src/receipts.dart';
import 'package:lacteva_mobile/src/pricing_resolution.dart';
import 'package:lacteva_mobile/src/rate_cards.dart';
import 'package:lacteva_mobile/src/settlements.dart';
import 'package:lacteva_mobile/src/suppliers.dart';
import 'package:qr_flutter/qr_flutter.dart';

class _FakeClient extends ApiClient {
  @override
  Future<List<BranchSummary>> listBranches() async => [
    BranchSummary(id: 'b1', name: 'Kilima Hill', code: 'KH'),
  ];
}

void main() {
  testWidgets('app starts on the login screen', (tester) async {
    await tester.pumpWidget(const LactevaApp());
    expect(find.text('Lacteva — Sign in'), findsOneWidget);
    expect(find.text('Sign in'), findsWidgets);
  });

  testWidgets('login form validates required fields', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(
          // DEMO-012: sign-in leads to the delivery round, which captures
          // into the durable queue — so the login screen takes the OFFLINE
          // client. A plain ApiClient would compile and then drop a round.
          client: OfflineApiClient(
            queue: SyncQueue(MemoryOfflineStore()),
            deviceId: 'test',
          ),
        ),
      ),
    );
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
      MaterialApp(
        home: ReadinessScreen(client: _ReadinessFake(), centerId: 'c1'),
      ),
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
    expect(find.text('Farmer code'), findsOneWidget);
    expect(find.text('Identify farmer'), findsOneWidget);
  });

  testWidgets('rate card form validates required fields', (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: RateCardFormScreen(client: ApiClient())),
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Currency (ISO 4217)'),
      'KESH',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pump();
    expect(find.text('Name needs at least 2 characters'), findsOneWidget);
    expect(find.text('Currency must be 3 letters'), findsOneWidget);
    expect(find.text('Enter a date as YYYY-MM-DD'), findsOneWidget);
  });

  testWidgets('rate card list shows status chips and effective range', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(home: RateCardsListScreen(client: _RateCardFake())),
    );
    await tester.pumpAndSettle();
    expect(find.text('Standard Milk Rates'), findsOneWidget);
    expect(find.text('published'), findsOneWidget);
    expect(find.textContaining('2026-09-01 → open'), findsOneWidget);
  });

  testWidgets('draft rate card detail offers submit and archive', (
    tester,
  ) async {
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

  testWidgets('published rate card detail offers new version only', (
    tester,
  ) async {
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
      find.widgetWithText(TextFormField, 'Product code'),
      'RAW-COW-MILK',
    );
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('FAT — Fat').last);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Reading value (e.g. 4.2)'),
      '4.2',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Resolve'));
    await tester.pumpAndSettle();
    expect(find.text('Rate card: MILK-STD v1'), findsOneWidget);
    expect(find.text('Unit price: 45 KES'), findsOneWidget);
    expect(find.text('Calculate gross amount'), findsOneWidget);
  });

  testWidgets('calculator computes gross with trace after resolution', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ResolutionTestScreen(client: _ResolveFake(), centerId: 'c1'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Product code'),
      'RAW-COW-MILK',
    );
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('FAT — Fat').last);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Reading value (e.g. 4.2)'),
      '4.2',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Resolve'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'Quantity (kg)'),
      '125.5',
    );
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
          client: _ResolveFake(failStage: 'band'),
          centerId: 'c1',
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Product code'),
      'RAW-COW-MILK',
    );
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('FAT — Fat').last);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Reading value (e.g. 4.2)'),
      '9.9',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Resolve'));
    await tester.pumpAndSettle();
    expect(find.text('No resolution (failed at: band)'), findsOneWidget);
    expect(find.textContaining('no band contains'), findsOneWidget);
  });

  testWidgets('settlement list shows periods and totals', (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: SettlementListScreen(client: _SettlementFake())),
    );
    await tester.pumpAndSettle();
    expect(find.text('STL-AB12CD'), findsOneWidget);
    expect(find.textContaining('net 7897.50 KES'), findsOneWidget);
    expect(find.text('calculated'), findsOneWidget);
  });

  testWidgets('calculated settlement detail offers finalize', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: SettlementDetailScreen(
          client: _SettlementFake(),
          settlementId: 's-calc',
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Calculate totals'), findsOneWidget);
    expect(find.text('Finalize'), findsOneWidget);
    expect(find.text('Lines (2)'), findsOneWidget);
    expect(find.text('125.5 kg @ 45'), findsOneWidget);
  });

  testWidgets('finalized settlement detail is read-only', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: SettlementDetailScreen(
          client: _SettlementFake(),
          settlementId: 's-final',
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Finalize'), findsNothing);
    expect(find.text('Calculate totals'), findsNothing);
    expect(find.text('Cancel settlement'), findsNothing);
  });

  testWidgets('finalize screen warns about permanence', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: FinalizeSettlementScreen(settlement: _SettlementFake.calculated),
      ),
    );
    expect(find.text('Net payable: 7897.50 KES'), findsOneWidget);
    expect(find.textContaining('cannot be undone'), findsOneWidget);
  });

  testWidgets('receipt history shows amount, number and supplier', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(home: ReceiptHistoryScreen(client: _ReceiptFake())),
    );
    await tester.pumpAndSettle();
    expect(find.text('7897.50 KES'), findsOneWidget);
    expect(find.textContaining('RCP-AB12CD'), findsOneWidget);
    expect(find.textContaining('Amina Njoroge'), findsOneWidget);
    expect(find.widgetWithText(Chip, 'generated'), findsOneWidget);
  });

  testWidgets('receipt detail previews the placeholder and offers download', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ReceiptDetailScreen(client: _ReceiptFake(), receiptId: 'r-1'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Settlements (1)'), findsOneWidget);
    expect(find.text('STL-OCT001'), findsOneWidget);
    // The placeholder must announce itself rather than look like a real PDF.
    expect(find.text('Placeholder artifact'), findsOneWidget);
    expect(find.textContaining('No PDF engine is integrated'), findsOneWidget);
    expect(find.textContaining('Download RCP-AB12CD.pdf.txt'), findsOneWidget);
  });

  testWidgets('payment history shows amount, method and status', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(home: PaymentHistoryScreen(client: _PaymentFake())),
    );
    await tester.pumpAndSettle();
    expect(find.text('7897.50 KES'), findsOneWidget);
    expect(find.textContaining('PAY-AB12CD'), findsOneWidget);
    expect(find.textContaining('bank transfer'), findsOneWidget);
    // "completed"/"failed" also label the filter chips, so target the status
    // chip on the row itself.
    expect(find.widgetWithText(Chip, 'completed'), findsOneWidget);
    expect(find.widgetWithText(Chip, 'failed'), findsOneWidget);
  });

  testWidgets('payment detail lists settlements and every attempt', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: PaymentDetailScreen(client: _PaymentFake(), paymentId: 'p-2'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Settlements paid (1)'), findsOneWidget);
    expect(find.text('STL-NOV001'), findsOneWidget);
    expect(find.text('Attempts (2)'), findsOneWidget);
    expect(find.text('Last failure'), findsOneWidget);
    expect(find.text('bank rejected the account'), findsWidgets);
  });

  testWidgets('notification history shows delivery status and recipient', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(home: NotificationHistoryScreen(client: _NotificationFake())),
    );
    await tester.pumpAndSettle();
    expect(find.text('Settlement STL-AB12CD ready'), findsOneWidget);
    expect(find.textContaining('+254700000001'), findsOneWidget);
    expect(find.text('×3'), findsOneWidget); // the retried one
  });

  testWidgets('notification detail explains which event caused the message', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: NotificationDetailScreen(notification: _NotificationFake.dead),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('settlement.finalized.v1'), findsOneWidget);
    expect(find.text('dead after 5 attempt(s)'), findsOneWidget);
    expect(find.text('provider rejected the number'), findsOneWidget);
  });

  testWidgets('center today summary shows tiles and pricing warning', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: CenterTodayScreen(client: _ReportFake(), centerId: 'c1'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('40.0 kg'), findsOneWidget);
    expect(find.text('1725.00 KES'), findsOneWidget);
    expect(find.text('2 / 1'), findsOneWidget);
    expect(find.text('3.94'), findsOneWidget);
    expect(find.text('1 accepted without pricing'), findsOneWidget);
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
      MaterialApp(
        home: CenterFormScreen(client: _FakeClient(), center: center),
      ),
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
      ReadinessResultView(
        status: 'WARNING',
        checks: [
          ReadinessCheckView(
            rule: 'center.active',
            severity: 'blocking',
            passed: true,
            detail: 'center status is active',
          ),
          ReadinessCheckView(
            rule: 'device.printer',
            severity: 'warning',
            passed: false,
            detail: '0 usable printer(s) of 0 active',
          ),
        ],
      );
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
      id: 'r1',
      fromValue: 3.0,
      toValue: 4.0,
      unitPrice: 40.0,
      active: true,
    ),
    MatrixRowView(
      id: 'r2',
      fromValue: 5.0,
      toValue: 6.0,
      unitPrice: 50.0,
      active: true,
    ),
  ];

  @override
  Future<MatrixPageResult> listMatrices({
    String query = '',
    String rateCardId = '',
    int limit = 20,
    int offset = 0,
  }) async => MatrixPageResult(items: [_summary], total: 1);

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
          {'from_value': 4.0, 'to_value': 5.0},
        ],
        editable: id == 'm-draft',
      );

  @override
  Future<List<DimensionSummary>> listQualityDimensions() async => [
    DimensionSummary(code: 'FAT', name: 'Fat', unit: '%', active: true),
    DimensionSummary(
      code: 'SNF',
      name: 'Solids-Not-Fat',
      unit: '%',
      active: true,
    ),
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
      throw ApiException(
        422,
        'No applicable pricing was found.',
        extra: {
          'stage': failStage,
          'reason': 'no band contains the reading $value',
        },
      );
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
  }) async => CalculationResultView(
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
        values: const {'raw_amount': '5647.500'},
      ),
      CalculationTraceStepView(
        operation: 'round',
        detail: 'HALF_UP to 2 decimal place(s)',
        values: const {'rounded_amount': '5647.50'},
      ),
    ],
  );
}

class _ReportFake extends ApiClient {
  @override
  Future<DailySummaryView> dailyReport(String centerId) async =>
      DailySummaryView(
        transactions: 3,
        accepted: 2,
        rejected: 1,
        suppliersServed: 1,
        totalNetWeightKg: 40.0,
        payable: '1725.00 KES',
        unpricedAccepted: 1,
        avgFat: 3.94,
        avgSnf: 8.5,
      );
}

class _SettlementFake extends ApiClient {
  static final calculated = SettlementSummary(
    id: 's-calc',
    number: 'STL-AB12CD',
    periodFrom: '2026-10-01',
    periodTo: '2026-10-31',
    currency: 'KES',
    grossAmount: '7897.50',
    netAmount: '7897.50',
    status: 'calculated',
    lineCount: 2,
  );

  static final _lines = [
    SettlementLineSummary(
      transactionDate: '2026-10-05',
      quantity: '125.5',
      quantityUnit: 'kg',
      unitPrice: '45',
      grossAmount: '5647.50',
    ),
    SettlementLineSummary(
      transactionDate: '2026-10-20',
      quantity: '50',
      quantityUnit: 'kg',
      unitPrice: '45',
      grossAmount: '2250.00',
    ),
  ];

  @override
  Future<SettlementPageResult> listSettlements({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) async => SettlementPageResult(items: [calculated], total: 1);

  @override
  Future<SettlementDetailResult> settlementDetail(String id) async =>
      SettlementDetailResult(
        settlement: id == 's-final'
            ? SettlementSummary(
                id: id,
                number: 'STL-FINAL1',
                periodFrom: '2026-09-01',
                periodTo: '2026-09-30',
                currency: 'KES',
                grossAmount: '1000.00',
                netAmount: '1000.00',
                status: 'finalized',
                lineCount: 2,
              )
            : calculated,
        lines: _lines,
        totalsMatch: true,
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
  }) async => RateCardPageResult(items: [_published], total: 1);

  @override
  Future<RateCardDetailResult> rateCardDetail(String id) async =>
      RateCardDetailResult(
        card: id == 'rc-1' ? _published : _draft,
        centerIds: const ['c1'],
        productCodes: id == 'rc-1' ? const ['RAW-COW-MILK'] : const [],
      );
}

class _NotificationFake extends ApiClient {
  static final sent = NotificationSummary(
    id: 'n-1',
    templateKey: 'settlement_finalized',
    eventName: 'settlement.finalized.v1',
    channel: 'sms',
    language: 'en',
    status: 'sent',
    attemptCount: 1,
    createdAt: '2026-08-04T09:15:00.123456',
    recipient: '+254700000001',
    title: 'Settlement STL-AB12CD ready',
    text: 'Hello Jane, settlement STL-AB12CD is finalised: 7897.50 KES.',
  );

  static final dead = NotificationSummary(
    id: 'n-2',
    templateKey: 'supplier_registered',
    eventName: 'settlement.finalized.v1',
    channel: 'sms',
    language: 'en',
    status: 'dead',
    attemptCount: 5,
    createdAt: '2026-08-04T09:20:00.000000',
    recipient: '+254700000002',
    title: 'Welcome to Kilima Dairy',
    text: 'Hello Peter, you are registered as supplier SUP-002.',
    error: 'provider rejected the number',
  );

  static final retried = NotificationSummary(
    id: 'n-3',
    templateKey: 'milk_rejected',
    eventName: 'milk.transaction.rejected.v1',
    channel: 'sms',
    language: 'en',
    status: 'sent',
    attemptCount: 3,
    createdAt: '2026-08-04T09:25:00.000000',
    recipient: '+254700000003',
    title: 'Delivery not accepted',
    text: 'Hello Amina, your delivery on 2026-08-04 was not accepted.',
  );

  @override
  Future<NotificationPageResult> listNotifications({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) async => NotificationPageResult(items: [sent, dead, retried], total: 3);
}

class _PaymentFake extends ApiClient {
  static final completed = PaymentSummary(
    id: 'p-1',
    number: 'PAY-AB12CD',
    currency: 'KES',
    method: 'BANK_TRANSFER',
    amount: '7897.50',
    status: 'completed',
    attemptCount: 1,
    lineCount: 1,
    createdAt: '2026-08-05T09:00:00.000000',
    reference: 'BNK-9911',
    completedAt: '2026-08-05T09:05:00.000000',
  );

  static final failed = PaymentSummary(
    id: 'p-2',
    number: 'PAY-EF34GH',
    currency: 'KES',
    method: 'MOBILE_MONEY',
    amount: '450.00',
    status: 'failed',
    attemptCount: 2,
    lineCount: 1,
    createdAt: '2026-08-05T10:00:00.000000',
    failureReason: 'bank rejected the account',
  );

  @override
  Future<PaymentPageResult> listPayments({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) async => PaymentPageResult(items: [completed, failed], total: 2);

  @override
  Future<PaymentDetailResult> paymentDetail(String id) async =>
      PaymentDetailResult(
        payment: failed,
        lines: [
          PaymentAllocation(settlementNumber: 'STL-NOV001', amount: '450.00'),
        ],
        attempts: [
          PaymentAttemptSummary(
            attemptNumber: 1,
            provider: 'MOBILE_MONEY',
            status: 'failed',
            startedAt: '2026-08-05T10:01:00.000000',
            failureReason: 'bank rejected the account',
          ),
          PaymentAttemptSummary(
            attemptNumber: 2,
            provider: 'MOBILE_MONEY',
            status: 'processing',
            startedAt: '2026-08-05T10:10:00.000000',
          ),
        ],
      );
}

class _ReceiptFake extends ApiClient {
  static final generated = ReceiptSummary(
    id: 'r-1',
    number: 'RCP-AB12CD',
    paymentNumber: 'PAY-AB12CD',
    supplierName: 'Amina Njoroge',
    supplierCode: 'S-000123',
    currency: 'KES',
    netAmount: '7897.50',
    status: 'generated',
    lineCount: 1,
    generatedAt: '2026-08-05T11:00:00.000000',
    paymentReference: 'MPESA-77',
    paymentMethod: 'MOBILE_MONEY',
  );

  @override
  Future<ReceiptPageResult> listReceipts({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) async => ReceiptPageResult(items: [generated], total: 1);

  @override
  Future<ReceiptDetailResult> receiptDetail(String id) async =>
      ReceiptDetailResult(
        receipt: generated,
        lines: [
          ReceiptLineSummary(
            settlementNumber: 'STL-OCT001',
            grossAmount: '7897.50',
            amountPaid: '7897.50',
            periodFrom: '2026-10-01',
            periodTo: '2026-10-31',
          ),
        ],
        availableFormats: ['html', 'json', 'pdf'],
      );

  @override
  Future<RenderedReceipt> renderReceipt(String id, String format) async =>
      RenderedReceipt(
        format: format,
        contentType: 'text/plain; charset=utf-8',
        filename: 'RCP-AB12CD.pdf.txt',
        body: 'LACTEVA RECEIPT — PDF PLACEHOLDER\nPAID 7897.50 KES',
        placeholder: format == 'pdf',
      );
}
