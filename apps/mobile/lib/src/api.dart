import 'dart:convert';

import 'package:http/http.dart' as http;

import '../main.dart' show apiUrl;

class ApiException implements Exception {
  ApiException(this.status, this.detail);
  final int status;
  final String detail;

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
      try {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        detail = (decoded['detail'] ?? decoded['title'] ?? detail).toString();
      } catch (_) {}
      throw ApiException(response.statusCode, detail);
    }
    if (response.body.isEmpty) return null;
    return jsonDecode(response.body);
  }

  Future<void> login(String email, String password, {String? tenantId}) async {
    final result = await _send('POST', '/v1/auth/token', body: {
      'email': email,
      'password': password,
      if (tenantId != null && tenantId.isNotEmpty) 'tenant_id': tenantId,
    }) as Map<String, dynamic>;
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
        await _send('GET', '/v1/collection-centers?$qs') as Map<String, dynamic>;
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
    final result = await _send('POST', '/v1/collection-centers', body: {
      'branch_id': branchId,
      'name': name,
      'code': code,
    }) as Map<String, dynamic>;
    return CenterSummary.fromJson(result);
  }

  Future<CenterSummary> updateCenter(
    String id, {
    required String name,
    required String timezone,
  }) async {
    final result = await _send('PUT', '/v1/collection-centers/$id', body: {
      'name': name,
      'timezone': timezone,
    }) as Map<String, dynamic>;
    return CenterSummary.fromJson(result);
  }

  Future<CenterDetail> centerDetail(String id) async {
    final result =
        await _send('GET', '/v1/collection-centers/$id') as Map<String, dynamic>;
    return CenterDetail.fromJson(result);
  }

  Future<CenterSummary> setStatus(String id, String status) async {
    final result = await _send('POST', '/v1/collection-centers/$id/status',
        body: {'status': status}) as Map<String, dynamic>;
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
    final result = await _send('GET', '/v1/suppliers?$qs') as Map<String, dynamic>;
    return SupplierPageResult.fromJson(result);
  }

  Future<SupplierSummary> createSupplier({
    required String fullName,
    required String phone,
    String village = '',
  }) async {
    final result = await _send('POST', '/v1/suppliers', body: {
      'full_name': fullName,
      'phone': phone,
      'village': village,
    }) as Map<String, dynamic>;
    return SupplierSummary.fromJson(result);
  }

  Future<void> updateSupplier(
    String id, {
    required String fullName,
    required String phone,
    String village = '',
  }) async {
    await _send('PUT', '/v1/suppliers/$id', body: {
      'full_name': fullName,
      'phone': phone,
      'village': village,
    });
  }

  Future<SupplierSummary> setSupplierStatus(String id, String status) async {
    final result = await _send('POST', '/v1/suppliers/$id/status',
        body: {'status': status}) as Map<String, dynamic>;
    return SupplierSummary.fromJson(result);
  }

  Future<SupplierDetailResult> supplierDetail(String id) async {
    final detail = await _send('GET', '/v1/suppliers/$id') as Map<String, dynamic>;
    final qr = await _send('GET', '/v1/suppliers/$id/qr') as Map<String, dynamic>;
    return SupplierDetailResult(
      supplier:
          SupplierSummary.fromJson(detail['supplier'] as Map<String, dynamic>),
      village: ((detail['profile'] as Map<String, dynamic>)['village'] ?? '')
          .toString(),
      centerIds: (detail['center_ids'] as List<dynamic>)
          .map((e) => e as String)
          .toList(),
      qrPayload: qr['payload'] as String,
    );
  }

  Future<Map<String, dynamic>> openCollectionSession(String centerId) async {
    return await _send('POST', '/v1/collection-sessions',
        body: {'center_id': centerId, 'label': 'mobile'}) as Map<String, dynamic>;
  }

  Future<List<Map<String, dynamic>>> listOpenSessions(String centerId) async {
    final result = await _send(
            'GET', '/v1/collection-sessions?center_id=$centerId&status=open')
        as List<dynamic>;
    return result.map((e) => e as Map<String, dynamic>).toList();
  }

  Future<Map<String, dynamic>> txStep(String path, {Object? body}) async {
    return await _send('POST', path, body: body ?? {}) as Map<String, dynamic>;
  }

  Future<ReadinessResultView> readiness(String centerId) async {
    final result = await _send('GET', '/v1/collection-centers/$centerId/readiness')
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
    final result = await _send('GET', '/v1/rate-cards?$qs') as Map<String, dynamic>;
    return RateCardPageResult.fromJson(result);
  }

  Future<RateCardSummary> createRateCard({
    required String name,
    required String currency,
    required String effectiveFrom,
    String? effectiveUntil,
    String description = '',
  }) async {
    final result = await _send('POST', '/v1/rate-cards', body: {
      'name': name,
      'currency': currency,
      'effective_from': effectiveFrom,
      'effective_until': effectiveUntil,
      'description': description,
    }) as Map<String, dynamic>;
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
    final result = await _send('PUT', '/v1/rate-cards/$id', body: {
      'name': name,
      'currency': currency,
      'effective_from': effectiveFrom,
      'effective_until': effectiveUntil,
      'description': description,
    }) as Map<String, dynamic>;
    return RateCardSummary.fromJson(result);
  }

  Future<RateCardDetailResult> rateCardDetail(String id) async {
    final result = await _send('GET', '/v1/rate-cards/$id') as Map<String, dynamic>;
    return RateCardDetailResult.fromJson(result);
  }

  /// Workflow: action is submit | approve | publish | archive | versions.
  Future<RateCardSummary> rateCardAction(String id, String action) async {
    final result =
        await _send('POST', '/v1/rate-cards/$id/$action', body: {}) as Map<String, dynamic>;
    return RateCardSummary.fromJson(result);
  }

  Future<void> assignRateCardCenter(String id, String centerId) async {
    await _send('POST', '/v1/rate-cards/$id/centers', body: {'center_id': centerId});
  }

  Future<void> assignRateCardProduct(String id, String productCode) async {
    await _send('POST', '/v1/rate-cards/$id/products',
        body: {'product_code': productCode});
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
  OperatingWindowView(
      {required this.dayOfWeek, required this.opens, required this.closes});

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

  factory RateCardSummary.fromJson(Map<String, dynamic> json) => RateCardSummary(
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
