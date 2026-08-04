import 'dart:convert';

import 'package:http/http.dart' as http;

import '../main.dart' show apiUrl;

class ApiException implements Exception {
  ApiException(this.status, this.detail, {this.extra});
  final int status;
  final String detail;

  /// Structured problem-detail payload (e.g. pricing resolution stage info).
  final Map<String, dynamic>? extra;

  @override
  String toString() => detail;
}

/// Thin API client for platform-core. Kept overridable for widget tests.
/// TODO(M2): offline queue + sync engine replaces direct calls (Collect R09).
class ApiClient {
  ApiClient({http.Client? inner}) : _http = inner ?? http.Client();

  final http.Client _http;
  String? _token;

  bool get isAuthenticated => _token != null;

  Map<String, String> get _headers => {
    'Content-Type': 'application/json',
    if (_token != null) 'Authorization': 'Bearer $_token',
  };

  Future<dynamic> _send(String method, String path, {Object? body}) async {
    final uri = Uri.parse('$apiUrl$path');
    final request = http.Request(method, uri)..headers.addAll(_headers);
    if (body != null) request.body = jsonEncode(body);
    final streamed = await _http.send(request);
    final response = await http.Response.fromStream(streamed);
    if (response.statusCode >= 400) {
      String detail = 'Request failed (${response.statusCode})';
      Map<String, dynamic>? extra;
      try {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        detail = (decoded['detail'] ?? decoded['title'] ?? detail).toString();
        if (decoded['extra'] is Map<String, dynamic>) {
          extra = decoded['extra'] as Map<String, dynamic>;
        }
      } catch (_) {}
      throw ApiException(response.statusCode, detail, extra: extra);
    }
    if (response.body.isEmpty) return null;
    return jsonDecode(response.body);
  }

  Future<void> login(String email, String password, {String? tenantId}) async {
    final result =
        await _send(
              'POST',
              '/v1/auth/token',
              body: {
                'email': email,
                'password': password,
                if (tenantId != null && tenantId.isNotEmpty)
                  'tenant_id': tenantId,
              },
            )
            as Map<String, dynamic>;
    _token = result['access_token'] as String;
  }

  Future<CenterPage> listCenters({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) async {
    final params = <String, String>{
      'limit': '$limit',
      'offset': '$offset',
      if (query.isNotEmpty) 'q': query,
      if (status.isNotEmpty) 'status': status,
    };
    final qs = Uri(queryParameters: params).query;
    final result =
        await _send('GET', '/v1/collection-centers?$qs')
            as Map<String, dynamic>;
    return CenterPage.fromJson(result);
  }

  Future<List<BranchSummary>> listBranches() async {
    final result = await _send('GET', '/v1/branches') as List<dynamic>;
    return result
        .map((e) => BranchSummary.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<CenterSummary> createCenter({
    required String branchId,
    required String name,
    required String code,
  }) async {
    final result =
        await _send(
              'POST',
              '/v1/collection-centers',
              body: {'branch_id': branchId, 'name': name, 'code': code},
            )
            as Map<String, dynamic>;
    return CenterSummary.fromJson(result);
  }

  Future<CenterSummary> updateCenter(
    String id, {
    required String name,
    required String timezone,
  }) async {
    final result =
        await _send(
              'PUT',
              '/v1/collection-centers/$id',
              body: {'name': name, 'timezone': timezone},
            )
            as Map<String, dynamic>;
    return CenterSummary.fromJson(result);
  }

  Future<CenterDetail> centerDetail(String id) async {
    final result =
        await _send('GET', '/v1/collection-centers/$id')
            as Map<String, dynamic>;
    return CenterDetail.fromJson(result);
  }

  Future<CenterSummary> setStatus(String id, String status) async {
    final result =
        await _send(
              'POST',
              '/v1/collection-centers/$id/status',
              body: {'status': status},
            )
            as Map<String, dynamic>;
    return CenterSummary.fromJson(result);
  }

  Future<SupplierPageResult> listSuppliers({
    String query = '',
    int limit = 20,
    int offset = 0,
  }) async {
    final params = <String, String>{
      'limit': '$limit',
      'offset': '$offset',
      if (query.isNotEmpty) 'q': query,
    };
    final qs = Uri(queryParameters: params).query;
    final result =
        await _send('GET', '/v1/suppliers?$qs') as Map<String, dynamic>;
    return SupplierPageResult.fromJson(result);
  }

  Future<SupplierSummary> createSupplier({
    required String fullName,
    required String phone,
    String village = '',
  }) async {
    final result =
        await _send(
              'POST',
              '/v1/suppliers',
              body: {'full_name': fullName, 'phone': phone, 'village': village},
            )
            as Map<String, dynamic>;
    return SupplierSummary.fromJson(result);
  }

  Future<void> updateSupplier(
    String id, {
    required String fullName,
    required String phone,
    String village = '',
  }) async {
    await _send(
      'PUT',
      '/v1/suppliers/$id',
      body: {'full_name': fullName, 'phone': phone, 'village': village},
    );
  }

  Future<SupplierSummary> setSupplierStatus(String id, String status) async {
    final result =
        await _send(
              'POST',
              '/v1/suppliers/$id/status',
              body: {'status': status},
            )
            as Map<String, dynamic>;
    return SupplierSummary.fromJson(result);
  }

  Future<SupplierDetailResult> supplierDetail(String id) async {
    final detail =
        await _send('GET', '/v1/suppliers/$id') as Map<String, dynamic>;
    final qr =
        await _send('GET', '/v1/suppliers/$id/qr') as Map<String, dynamic>;
    return SupplierDetailResult(
      supplier: SupplierSummary.fromJson(
        detail['supplier'] as Map<String, dynamic>,
      ),
      village: ((detail['profile'] as Map<String, dynamic>)['village'] ?? '')
          .toString(),
      centerIds: (detail['center_ids'] as List<dynamic>)
          .map((e) => e as String)
          .toList(),
      qrPayload: qr['payload'] as String,
    );
  }

  Future<Map<String, dynamic>> openCollectionSession(String centerId) async {
    return await _send(
          'POST',
          '/v1/collection-sessions',
          body: {'center_id': centerId, 'label': 'mobile'},
        )
        as Map<String, dynamic>;
  }

  Future<List<Map<String, dynamic>>> listOpenSessions(String centerId) async {
    final result =
        await _send(
              'GET',
              '/v1/collection-sessions?center_id=$centerId&status=open',
            )
            as List<dynamic>;
    return result.map((e) => e as Map<String, dynamic>).toList();
  }

  Future<Map<String, dynamic>> txStep(String path, {Object? body}) async {
    return await _send('POST', path, body: body ?? {}) as Map<String, dynamic>;
  }

  Future<ReadinessResultView> readiness(String centerId) async {
    final result =
        await _send('GET', '/v1/collection-centers/$centerId/readiness')
            as Map<String, dynamic>;
    return ReadinessResultView.fromJson(result);
  }

  Future<RateCardPageResult> listRateCards({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) async {
    final params = <String, String>{
      'limit': '$limit',
      'offset': '$offset',
      if (query.isNotEmpty) 'q': query,
      if (status.isNotEmpty) 'status': status,
    };
    final qs = Uri(queryParameters: params).query;
    final result =
        await _send('GET', '/v1/rate-cards?$qs') as Map<String, dynamic>;
    return RateCardPageResult.fromJson(result);
  }

  Future<RateCardSummary> createRateCard({
    required String name,
    required String currency,
    required String effectiveFrom,
    String? effectiveUntil,
    String description = '',
  }) async {
    final result =
        await _send(
              'POST',
              '/v1/rate-cards',
              body: {
                'name': name,
                'currency': currency,
                'effective_from': effectiveFrom,
                'effective_until': effectiveUntil,
                'description': description,
              },
            )
            as Map<String, dynamic>;
    return RateCardSummary.fromJson(result);
  }

  Future<RateCardSummary> updateRateCard(
    String id, {
    required String name,
    required String currency,
    required String effectiveFrom,
    String? effectiveUntil,
    String description = '',
  }) async {
    final result =
        await _send(
              'PUT',
              '/v1/rate-cards/$id',
              body: {
                'name': name,
                'currency': currency,
                'effective_from': effectiveFrom,
                'effective_until': effectiveUntil,
                'description': description,
              },
            )
            as Map<String, dynamic>;
    return RateCardSummary.fromJson(result);
  }

  Future<RateCardDetailResult> rateCardDetail(String id) async {
    final result =
        await _send('GET', '/v1/rate-cards/$id') as Map<String, dynamic>;
    return RateCardDetailResult.fromJson(result);
  }

  /// Workflow: action is submit | approve | publish | archive | versions.
  Future<RateCardSummary> rateCardAction(String id, String action) async {
    final result =
        await _send('POST', '/v1/rate-cards/$id/$action', body: {})
            as Map<String, dynamic>;
    return RateCardSummary.fromJson(result);
  }

  Future<void> assignRateCardCenter(String id, String centerId) async {
    await _send(
      'POST',
      '/v1/rate-cards/$id/centers',
      body: {'center_id': centerId},
    );
  }

  Future<void> assignRateCardProduct(String id, String productCode) async {
    await _send(
      'POST',
      '/v1/rate-cards/$id/products',
      body: {'product_code': productCode},
    );
  }

  Future<List<DimensionSummary>> listQualityDimensions() async {
    final result =
        await _send('GET', '/v1/quality-dimensions') as List<dynamic>;
    return result
        .map((e) => DimensionSummary.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<MatrixPageResult> listMatrices({
    String query = '',
    String rateCardId = '',
    int limit = 20,
    int offset = 0,
  }) async {
    final params = <String, String>{
      'limit': '$limit',
      'offset': '$offset',
      if (query.isNotEmpty) 'q': query,
      if (rateCardId.isNotEmpty) 'rate_card_id': rateCardId,
    };
    final qs = Uri(queryParameters: params).query;
    final result =
        await _send('GET', '/v1/pricing-matrices?$qs') as Map<String, dynamic>;
    return MatrixPageResult.fromJson(result);
  }

  Future<MatrixSummary> createMatrix({
    required String rateCardId,
    required String name,
    required String productCode,
    required String dimensionCode,
    String productName = '',
  }) async {
    final result =
        await _send(
              'POST',
              '/v1/pricing-matrices',
              body: {
                'rate_card_id': rateCardId,
                'name': name,
                'product_code': productCode,
                'product_name': productName,
                'dimension_code': dimensionCode,
              },
            )
            as Map<String, dynamic>;
    return MatrixSummary.fromJson(result);
  }

  Future<MatrixDetailResult> matrixDetail(String id) async {
    final result =
        await _send('GET', '/v1/pricing-matrices/$id') as Map<String, dynamic>;
    return MatrixDetailResult.fromJson(result);
  }

  Future<void> deleteMatrix(String id) async {
    await _send('DELETE', '/v1/pricing-matrices/$id');
  }

  Future<MatrixRowView> addMatrixRow(
    String matrixId, {
    required double fromValue,
    required double toValue,
    required double unitPrice,
  }) async {
    final result =
        await _send(
              'POST',
              '/v1/pricing-matrices/$matrixId/rows',
              body: {
                'from_value': fromValue,
                'to_value': toValue,
                'unit_price': unitPrice,
              },
            )
            as Map<String, dynamic>;
    return MatrixRowView.fromJson(result);
  }

  Future<MatrixRowView> updateMatrixRow(
    String matrixId,
    String rowId, {
    required double fromValue,
    required double toValue,
    required double unitPrice,
    bool active = true,
  }) async {
    final result =
        await _send(
              'PUT',
              '/v1/pricing-matrices/$matrixId/rows/$rowId',
              body: {
                'from_value': fromValue,
                'to_value': toValue,
                'unit_price': unitPrice,
                'active': active,
              },
            )
            as Map<String, dynamic>;
    return MatrixRowView.fromJson(result);
  }

  Future<void> deleteMatrixRow(String matrixId, String rowId) async {
    await _send('DELETE', '/v1/pricing-matrices/$matrixId/rows/$rowId');
  }

  /// Lightweight center summary for operators (REP-001). Defaults to today.
  Future<DailySummaryView> dailyReport(String centerId) async {
    final result =
        await _send('GET', '/v1/reports/collection/daily?center_id=$centerId')
            as Map<String, dynamic>;
    return DailySummaryView.fromJson(result);
  }

  Future<SettlementPageResult> listSettlements({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) async {
    final params = <String, String>{
      'limit': '$limit',
      'offset': '$offset',
      if (query.isNotEmpty) 'q': query,
      if (status.isNotEmpty) 'status': status,
    };
    final qs = Uri(queryParameters: params).query;
    final result =
        await _send('GET', '/v1/settlements?$qs') as Map<String, dynamic>;
    return SettlementPageResult.fromJson(result);
  }

  Future<SettlementDetailResult> settlementDetail(String id) async {
    final result =
        await _send('GET', '/v1/settlements/$id') as Map<String, dynamic>;
    return SettlementDetailResult.fromJson(result);
  }

  /// action: calculate | finalize | cancel
  Future<SettlementSummary> settlementAction(String id, String action) async {
    final result =
        await _send('POST', '/v1/settlements/$id/$action', body: {})
            as Map<String, dynamic>;
    return SettlementSummary.fromJson(result);
  }

  /// Payment history (PAY-001). Read-only on mobile: the app shows what was
  /// paid, it never executes a payment.
  Future<PaymentPageResult> listPayments({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) async {
    final params = <String, String>{
      'limit': '$limit',
      'offset': '$offset',
      if (query.isNotEmpty) 'q': query,
      if (status.isNotEmpty) 'status': status,
    };
    final qs = Uri(queryParameters: params).query;
    final result =
        await _send('GET', '/v1/payments?$qs') as Map<String, dynamic>;
    return PaymentPageResult.fromJson(result);
  }

  Future<PaymentDetailResult> paymentDetail(String id) async {
    final result =
        await _send('GET', '/v1/payments/$id') as Map<String, dynamic>;
    return PaymentDetailResult.fromJson(result);
  }

  /// Notification delivery history (NOT-001). Read-only on mobile: the app
  /// shows what was sent, it never sends. No push notifications.
  Future<NotificationPageResult> listNotifications({
    String query = '',
    String status = '',
    int limit = 20,
    int offset = 0,
  }) async {
    final params = <String, String>{
      'limit': '$limit',
      'offset': '$offset',
      if (query.isNotEmpty) 'q': query,
      if (status.isNotEmpty) 'status': status,
    };
    final qs = Uri(queryParameters: params).query;
    final result =
        await _send('GET', '/v1/notifications?$qs') as Map<String, dynamic>;
    return NotificationPageResult.fromJson(result);
  }

  /// Pricing calculation (PRC-004): gross = unit price x quantity for a
  /// previously resolved band. Decimal math server-side, full trace back.
  Future<CalculationResultView> calculatePricing({
    required String rowId,
    required double quantity,
    required String transactionDate,
    String quantityUnit = 'kg',
    String? roundingPolicy,
  }) async {
    final result =
        await _send(
              'POST',
              '/v1/pricing/calculate',
              body: {
                'row_id': rowId,
                'quantity': quantity,
                'quantity_unit': quantityUnit,
                'transaction_date': transactionDate,
                'rounding_policy': ?roundingPolicy,
              },
            )
            as Map<String, dynamic>;
    return CalculationResultView.fromJson(result);
  }

  /// Read-side pricing resolution (PRC-003). Throws [ApiException] with a
  /// structured `extra` map ({stage, reason, inputs}) when nothing matches.
  Future<ResolutionResultView> resolvePricing({
    required String centerId,
    required String productCode,
    required String transactionDate,
    required String dimensionCode,
    required double value,
  }) async {
    final result =
        await _send(
              'POST',
              '/v1/pricing/resolve',
              body: {
                'center_id': centerId,
                'product_code': productCode,
                'transaction_date': transactionDate,
                'dimension_code': dimensionCode,
                'value': value,
              },
            )
            as Map<String, dynamic>;
    return ResolutionResultView.fromJson(result);
  }
}

class CenterSummary {
  CenterSummary({
    required this.id,
    required this.branchId,
    required this.name,
    required this.code,
    required this.status,
    required this.timezone,
  });

  factory CenterSummary.fromJson(Map<String, dynamic> json) => CenterSummary(
    id: json['id'] as String,
    branchId: json['branch_id'] as String,
    name: json['name'] as String,
    code: json['code'] as String,
    status: json['status'] as String,
    timezone: json['timezone'] as String,
  );

  final String id;
  final String branchId;
  final String name;
  final String code;
  final String status;
  final String timezone;
}

class CenterPage {
  CenterPage({required this.items, required this.total});

  factory CenterPage.fromJson(Map<String, dynamic> json) => CenterPage(
    items: (json['items'] as List<dynamic>)
        .map((e) => CenterSummary.fromJson(e as Map<String, dynamic>))
        .toList(),
    total: json['total'] as int,
  );

  final List<CenterSummary> items;
  final int total;
}

class BranchSummary {
  BranchSummary({required this.id, required this.name, required this.code});

  factory BranchSummary.fromJson(Map<String, dynamic> json) => BranchSummary(
    id: json['id'] as String,
    name: json['name'] as String,
    code: json['code'] as String,
  );

  final String id;
  final String name;
  final String code;
}

class OperatingWindowView {
  OperatingWindowView({
    required this.dayOfWeek,
    required this.opens,
    required this.closes,
  });

  factory OperatingWindowView.fromJson(Map<String, dynamic> json) =>
      OperatingWindowView(
        dayOfWeek: json['day_of_week'] as int,
        opens: json['opens'] as String,
        closes: json['closes'] as String,
      );

  static const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  final int dayOfWeek;
  final String opens;
  final String closes;

  String get label => '${dayNames[dayOfWeek]}  $opens – $closes';
}

class CenterDetail {
  CenterDetail({
    required this.center,
    required this.settings,
    required this.windows,
    required this.calendar,
  });

  factory CenterDetail.fromJson(Map<String, dynamic> json) => CenterDetail(
    center: CenterSummary.fromJson(json['center'] as Map<String, dynamic>),
    settings: (json['settings'] as Map<String, dynamic>?) ?? const {},
    windows: (json['operating_windows'] as List<dynamic>)
        .map((e) => OperatingWindowView.fromJson(e as Map<String, dynamic>))
        .toList(),
    calendar: (json['calendar'] as List<dynamic>)
        .map((e) => e as Map<String, dynamic>)
        .toList(),
  );

  final CenterSummary center;
  final Map<String, dynamic> settings;
  final List<OperatingWindowView> windows;
  final List<Map<String, dynamic>> calendar;
}

class ReadinessCheckView {
  ReadinessCheckView({
    required this.rule,
    required this.severity,
    required this.passed,
    required this.detail,
  });

  factory ReadinessCheckView.fromJson(Map<String, dynamic> json) =>
      ReadinessCheckView(
        rule: json['rule'] as String,
        severity: json['severity'] as String,
        passed: json['passed'] as bool,
        detail: json['detail'] as String,
      );

  final String rule;
  final String severity;
  final bool passed;
  final String detail;
}

class ReadinessResultView {
  ReadinessResultView({required this.status, required this.checks});

  factory ReadinessResultView.fromJson(Map<String, dynamic> json) =>
      ReadinessResultView(
        status: json['status'] as String,
        checks: (json['checks'] as List<dynamic>)
            .map((e) => ReadinessCheckView.fromJson(e as Map<String, dynamic>))
            .toList(),
      );

  final String status;
  final List<ReadinessCheckView> checks;
}

class SupplierSummary {
  SupplierSummary({
    required this.id,
    required this.code,
    required this.status,
    required this.fullName,
    required this.phone,
  });

  factory SupplierSummary.fromJson(Map<String, dynamic> json) =>
      SupplierSummary(
        id: json['id'] as String,
        code: json['code'] as String,
        status: json['status'] as String,
        fullName: json['full_name'] as String,
        phone: json['phone'] as String,
      );

  final String id;
  final String code;
  final String status;
  final String fullName;
  final String phone;
}

class SupplierPageResult {
  SupplierPageResult({required this.items, required this.total});

  factory SupplierPageResult.fromJson(Map<String, dynamic> json) =>
      SupplierPageResult(
        items: (json['items'] as List<dynamic>)
            .map((e) => SupplierSummary.fromJson(e as Map<String, dynamic>))
            .toList(),
        total: json['total'] as int,
      );

  final List<SupplierSummary> items;
  final int total;
}

class SupplierDetailResult {
  SupplierDetailResult({
    required this.supplier,
    required this.village,
    required this.centerIds,
    required this.qrPayload,
  });

  final SupplierSummary supplier;
  final String village;
  final List<String> centerIds;
  final String qrPayload;
}

class RateCardSummary {
  RateCardSummary({
    required this.id,
    required this.code,
    required this.name,
    required this.description,
    required this.currency,
    required this.effectiveFrom,
    required this.effectiveUntil,
    required this.status,
    required this.version,
  });

  factory RateCardSummary.fromJson(Map<String, dynamic> json) =>
      RateCardSummary(
        id: json['id'] as String,
        code: json['code'] as String,
        name: json['name'] as String,
        description: (json['description'] ?? '').toString(),
        currency: json['currency'] as String,
        effectiveFrom: json['effective_from'] as String,
        effectiveUntil: json['effective_until'] as String?,
        status: json['status'] as String,
        version: json['version'] as int,
      );

  final String id;
  final String code;
  final String name;
  final String description;
  final String currency;
  final String effectiveFrom;
  final String? effectiveUntil;
  final String status;
  final int version;

  String get effectiveLabel => '$effectiveFrom → ${effectiveUntil ?? 'open'}';
}

class RateCardPageResult {
  RateCardPageResult({required this.items, required this.total});

  factory RateCardPageResult.fromJson(Map<String, dynamic> json) =>
      RateCardPageResult(
        items: (json['items'] as List<dynamic>)
            .map((e) => RateCardSummary.fromJson(e as Map<String, dynamic>))
            .toList(),
        total: json['total'] as int,
      );

  final List<RateCardSummary> items;
  final int total;
}

class DimensionSummary {
  DimensionSummary({
    required this.code,
    required this.name,
    required this.unit,
    required this.active,
  });

  factory DimensionSummary.fromJson(Map<String, dynamic> json) =>
      DimensionSummary(
        code: json['code'] as String,
        name: json['name'] as String,
        unit: (json['unit'] ?? '').toString(),
        active: json['active'] as bool,
      );

  final String code;
  final String name;
  final String unit;
  final bool active;
}

class MatrixSummary {
  MatrixSummary({
    required this.id,
    required this.rateCardCode,
    required this.name,
    required this.productCode,
    required this.productName,
    required this.dimensionCode,
    required this.status,
    required this.version,
    required this.rowCount,
  });

  factory MatrixSummary.fromJson(Map<String, dynamic> json) => MatrixSummary(
    id: json['id'] as String,
    rateCardCode: json['rate_card_code'] as String,
    name: json['name'] as String,
    productCode: json['product_code'] as String,
    productName: (json['product_name'] ?? '').toString(),
    dimensionCode: json['dimension_code'] as String,
    status: json['status'] as String,
    version: json['version'] as int,
    rowCount: json['row_count'] as int,
  );

  final String id;
  final String rateCardCode;
  final String name;
  final String productCode;
  final String productName;
  final String dimensionCode;
  final String status;
  final int version;
  final int rowCount;
}

class MatrixPageResult {
  MatrixPageResult({required this.items, required this.total});

  factory MatrixPageResult.fromJson(Map<String, dynamic> json) =>
      MatrixPageResult(
        items: (json['items'] as List<dynamic>)
            .map((e) => MatrixSummary.fromJson(e as Map<String, dynamic>))
            .toList(),
        total: json['total'] as int,
      );

  final List<MatrixSummary> items;
  final int total;
}

class MatrixRowView {
  MatrixRowView({
    required this.id,
    required this.fromValue,
    required this.toValue,
    required this.unitPrice,
    required this.active,
  });

  factory MatrixRowView.fromJson(Map<String, dynamic> json) => MatrixRowView(
    id: json['id'] as String,
    fromValue: (json['from_value'] as num).toDouble(),
    toValue: (json['to_value'] as num).toDouble(),
    unitPrice: (json['unit_price'] as num).toDouble(),
    active: json['active'] as bool,
  );

  final String id;
  final double fromValue;
  final double toValue;
  final double unitPrice;
  final bool active;
}

class MatrixDetailResult {
  MatrixDetailResult({
    required this.matrix,
    required this.dimensionLabel,
    required this.rows,
    required this.gaps,
    required this.editable,
  });

  factory MatrixDetailResult.fromJson(Map<String, dynamic> json) {
    final dim = json['dimension'] as Map<String, dynamic>;
    return MatrixDetailResult(
      matrix: MatrixSummary.fromJson(json['matrix'] as Map<String, dynamic>),
      dimensionLabel:
          '${dim['code']}${(dim['unit'] ?? '') != '' ? ' (${dim['unit']})' : ''}',
      rows: (json['rows'] as List<dynamic>)
          .map((e) => MatrixRowView.fromJson(e as Map<String, dynamic>))
          .toList(),
      gaps: (json['gaps'] as List<dynamic>)
          .map((e) => e as Map<String, dynamic>)
          .toList(),
      editable: json['editable'] as bool,
    );
  }

  final MatrixSummary matrix;
  final String dimensionLabel;
  final List<MatrixRowView> rows;
  final List<Map<String, dynamic>> gaps;
  final bool editable;
}

class DailySummaryView {
  DailySummaryView({
    required this.transactions,
    required this.accepted,
    required this.rejected,
    required this.suppliersServed,
    required this.totalNetWeightKg,
    required this.payable,
    required this.unpricedAccepted,
    required this.avgFat,
    required this.avgSnf,
  });

  factory DailySummaryView.fromJson(Map<String, dynamic> json) {
    final payableMap = (json['payable_by_currency'] as Map<String, dynamic>);
    return DailySummaryView(
      transactions: json['transactions'] as int,
      accepted: json['accepted'] as int,
      rejected: json['rejected'] as int,
      suppliersServed: json['suppliers_served'] as int,
      totalNetWeightKg: (json['total_net_weight_kg'] as num).toDouble(),
      payable: payableMap.entries.map((e) => '${e.value} ${e.key}').join(' · '),
      unpricedAccepted: json['unpriced_accepted'] as int,
      avgFat: (json['weighted_avg_fat'] as num?)?.toDouble(),
      avgSnf: (json['weighted_avg_snf'] as num?)?.toDouble(),
    );
  }

  final int transactions;
  final int accepted;
  final int rejected;
  final int suppliersServed;
  final double totalNetWeightKg;
  final String payable;
  final int unpricedAccepted;
  final double? avgFat;
  final double? avgSnf;
}

class SettlementSummary {
  SettlementSummary({
    required this.id,
    required this.number,
    required this.periodFrom,
    required this.periodTo,
    required this.currency,
    required this.grossAmount,
    required this.netAmount,
    required this.status,
    required this.lineCount,
  });

  factory SettlementSummary.fromJson(Map<String, dynamic> json) =>
      SettlementSummary(
        id: json['id'] as String,
        number: json['settlement_number'] as String,
        periodFrom: json['period_from'] as String,
        periodTo: json['period_to'] as String,
        currency: json['currency'] as String,
        grossAmount: json['gross_amount'].toString(),
        netAmount: json['net_amount'].toString(),
        status: json['status'] as String,
        lineCount: json['line_count'] as int,
      );

  final String id;
  final String number;
  final String periodFrom;
  final String periodTo;
  final String currency;
  final String grossAmount;
  final String netAmount;
  final String status;
  final int lineCount;
}

class SettlementPageResult {
  SettlementPageResult({required this.items, required this.total});

  factory SettlementPageResult.fromJson(Map<String, dynamic> json) =>
      SettlementPageResult(
        items: (json['items'] as List<dynamic>)
            .map((e) => SettlementSummary.fromJson(e as Map<String, dynamic>))
            .toList(),
        total: json['total'] as int,
      );

  final List<SettlementSummary> items;
  final int total;
}

class SettlementLineSummary {
  SettlementLineSummary({
    required this.transactionDate,
    required this.quantity,
    required this.quantityUnit,
    required this.unitPrice,
    required this.grossAmount,
  });

  factory SettlementLineSummary.fromJson(Map<String, dynamic> json) =>
      SettlementLineSummary(
        transactionDate: json['transaction_date'] as String,
        quantity: json['quantity'].toString(),
        quantityUnit: (json['quantity_unit'] ?? '').toString(),
        unitPrice: json['unit_price'].toString(),
        grossAmount: json['gross_amount'].toString(),
      );

  final String transactionDate;
  final String quantity;
  final String quantityUnit;
  final String unitPrice;
  final String grossAmount;
}

class SettlementDetailResult {
  SettlementDetailResult({
    required this.settlement,
    required this.lines,
    required this.totalsMatch,
  });

  factory SettlementDetailResult.fromJson(Map<String, dynamic> json) =>
      SettlementDetailResult(
        settlement: SettlementSummary.fromJson(
          json['settlement'] as Map<String, dynamic>,
        ),
        lines: (json['lines'] as List<dynamic>)
            .map(
              (e) => SettlementLineSummary.fromJson(e as Map<String, dynamic>),
            )
            .toList(),
        totalsMatch: json['totals_match_lines'] as bool,
      );

  final SettlementSummary settlement;
  final List<SettlementLineSummary> lines;
  final bool totalsMatch;
}

class CalculationTraceStepView {
  CalculationTraceStepView({
    required this.operation,
    required this.detail,
    required this.values,
  });

  factory CalculationTraceStepView.fromJson(Map<String, dynamic> json) =>
      CalculationTraceStepView(
        operation: json['operation'] as String,
        detail: json['detail'] as String,
        values: (json['values'] as Map<String, dynamic>).map(
          (k, v) => MapEntry(k, v.toString()),
        ),
      );

  final String operation;
  final String detail;
  final Map<String, String> values;
}

class CalculationResultView {
  CalculationResultView({
    required this.grossAmount,
    required this.unitPrice,
    required this.currency,
    required this.quantityValue,
    required this.quantityUnit,
    required this.roundingPolicy,
    required this.calculatorVersion,
    required this.trace,
  });

  factory CalculationResultView.fromJson(Map<String, dynamic> json) {
    final price = json['unit_price'] as Map<String, dynamic>;
    final gross = json['gross_amount'] as Map<String, dynamic>;
    final quantity = json['quantity'] as Map<String, dynamic>;
    return CalculationResultView(
      grossAmount: gross['amount'].toString(),
      unitPrice: price['amount'].toString(),
      currency: json['currency'] as String,
      quantityValue: (quantity['value'] as num).toDouble(),
      quantityUnit: (quantity['unit'] ?? '').toString(),
      roundingPolicy: json['rounding_policy'] as String,
      calculatorVersion: json['calculator_version'] as String,
      trace: (json['trace'] as List<dynamic>)
          .map(
            (e) => CalculationTraceStepView.fromJson(e as Map<String, dynamic>),
          )
          .toList(),
    );
  }

  final String grossAmount;
  final String unitPrice;
  final String currency;
  final double quantityValue;
  final String quantityUnit;
  final String roundingPolicy;
  final String calculatorVersion;
  final List<CalculationTraceStepView> trace;
}

class ResolutionResultView {
  ResolutionResultView({
    required this.rowId,
    required this.rateCardCode,
    required this.rateCardVersion,
    required this.matrixName,
    required this.rangeFrom,
    required this.rangeTo,
    required this.priceAmount,
    required this.currency,
    required this.readingValue,
    required this.readingUnit,
  });

  factory ResolutionResultView.fromJson(Map<String, dynamic> json) {
    final range = json['matching_range'] as Map<String, dynamic>;
    final price = json['unit_price'] as Map<String, dynamic>;
    final reading = json['reading'] as Map<String, dynamic>;
    return ResolutionResultView(
      rowId: json['row_id'] as String,
      rateCardCode: json['rate_card_code'] as String,
      rateCardVersion: json['rate_card_version'] as int,
      matrixName: json['matrix_name'] as String,
      rangeFrom: (range['from_value'] as num).toDouble(),
      rangeTo: (range['to_value'] as num).toDouble(),
      priceAmount: price['amount'].toString(),
      currency: price['currency'] as String,
      readingValue: (reading['value'] as num).toDouble(),
      readingUnit: (reading['unit'] ?? '').toString(),
    );
  }

  final String rowId;
  final String rateCardCode;
  final int rateCardVersion;
  final String matrixName;
  final double rangeFrom;
  final double rangeTo;
  final String priceAmount;
  final String currency;
  final double readingValue;
  final String readingUnit;
}

class RateCardDetailResult {
  RateCardDetailResult({
    required this.card,
    required this.centerIds,
    required this.productCodes,
  });

  factory RateCardDetailResult.fromJson(Map<String, dynamic> json) =>
      RateCardDetailResult(
        card: RateCardSummary.fromJson(json['card'] as Map<String, dynamic>),
        centerIds: (json['center_ids'] as List<dynamic>)
            .map((e) => e as String)
            .toList(),
        productCodes: (json['products'] as List<dynamic>)
            .map((e) => (e as Map<String, dynamic>)['product_code'] as String)
            .toList(),
      );

  final RateCardSummary card;
  final List<String> centerIds;
  final List<String> productCodes;
}

class NotificationSummary {
  NotificationSummary({
    required this.id,
    required this.templateKey,
    required this.eventName,
    required this.channel,
    required this.language,
    required this.status,
    required this.attemptCount,
    required this.createdAt,
    this.recipient,
    this.title,
    this.text,
    this.error,
  });

  factory NotificationSummary.fromJson(Map<String, dynamic> json) =>
      NotificationSummary(
        id: json['id'] as String,
        templateKey: json['template_key'] as String,
        eventName: json['event_name'] as String,
        channel: json['channel'] as String,
        language: json['language'] as String,
        status: json['status'] as String,
        attemptCount: json['attempt_count'] as int,
        createdAt: json['created_at'] as String,
        recipient: json['recipient'] as String?,
        title: json['title'] as String?,
        text: json['rendered_text'] as String?,
        error: json['error'] as String?,
      );

  final String id;
  final String templateKey;
  final String eventName;
  final String channel;
  final String language;
  final String status;
  final int attemptCount;
  final String createdAt;
  final String? recipient;
  final String? title;
  final String? text;
  final String? error;
}

class NotificationPageResult {
  NotificationPageResult({required this.items, required this.total});

  factory NotificationPageResult.fromJson(Map<String, dynamic> json) =>
      NotificationPageResult(
        items: (json['items'] as List<dynamic>)
            .map((e) => NotificationSummary.fromJson(e as Map<String, dynamic>))
            .toList(),
        total: json['total'] as int,
      );

  final List<NotificationSummary> items;
  final int total;
}

class PaymentSummary {
  PaymentSummary({
    required this.id,
    required this.number,
    required this.currency,
    required this.method,
    required this.amount,
    required this.status,
    required this.attemptCount,
    required this.lineCount,
    required this.createdAt,
    this.reference,
    this.failureReason,
    this.completedAt,
  });

  factory PaymentSummary.fromJson(Map<String, dynamic> json) => PaymentSummary(
    id: json['id'] as String,
    number: json['payment_number'] as String,
    currency: json['currency'] as String,
    method: json['method'] as String,
    amount: json['amount'].toString(),
    status: json['status'] as String,
    attemptCount: json['attempt_count'] as int,
    lineCount: json['line_count'] as int,
    createdAt: json['created_at'] as String,
    reference: json['reference'] as String?,
    failureReason: json['failure_reason'] as String?,
    completedAt: json['completed_at'] as String?,
  );

  final String id;
  final String number;
  final String currency;
  final String method;
  final String amount;
  final String status;
  final int attemptCount;
  final int lineCount;
  final String createdAt;
  final String? reference;
  final String? failureReason;
  final String? completedAt;
}

class PaymentPageResult {
  PaymentPageResult({required this.items, required this.total});

  factory PaymentPageResult.fromJson(Map<String, dynamic> json) =>
      PaymentPageResult(
        items: (json['items'] as List<dynamic>)
            .map((e) => PaymentSummary.fromJson(e as Map<String, dynamic>))
            .toList(),
        total: json['total'] as int,
      );

  final List<PaymentSummary> items;
  final int total;
}

class PaymentAllocation {
  PaymentAllocation({required this.settlementNumber, required this.amount});

  factory PaymentAllocation.fromJson(Map<String, dynamic> json) =>
      PaymentAllocation(
        settlementNumber: json['settlement_number'] as String,
        amount: json['amount'].toString(),
      );

  final String settlementNumber;
  final String amount;
}

class PaymentAttemptSummary {
  PaymentAttemptSummary({
    required this.attemptNumber,
    required this.provider,
    required this.status,
    required this.startedAt,
    this.reference,
    this.failureReason,
  });

  factory PaymentAttemptSummary.fromJson(Map<String, dynamic> json) =>
      PaymentAttemptSummary(
        attemptNumber: json['attempt_number'] as int,
        provider: json['provider'] as String,
        status: json['status'] as String,
        startedAt: json['started_at'] as String,
        reference: json['reference'] as String?,
        failureReason: json['failure_reason'] as String?,
      );

  final int attemptNumber;
  final String provider;
  final String status;
  final String startedAt;
  final String? reference;
  final String? failureReason;
}

class PaymentDetailResult {
  PaymentDetailResult({
    required this.payment,
    required this.lines,
    required this.attempts,
  });

  factory PaymentDetailResult.fromJson(
    Map<String, dynamic> json,
  ) => PaymentDetailResult(
    payment: PaymentSummary.fromJson(json['payment'] as Map<String, dynamic>),
    lines: (json['lines'] as List<dynamic>)
        .map((e) => PaymentAllocation.fromJson(e as Map<String, dynamic>))
        .toList(),
    attempts: (json['attempts'] as List<dynamic>)
        .map((e) => PaymentAttemptSummary.fromJson(e as Map<String, dynamic>))
        .toList(),
  );

  final PaymentSummary payment;
  final List<PaymentAllocation> lines;
  final List<PaymentAttemptSummary> attempts;
}
