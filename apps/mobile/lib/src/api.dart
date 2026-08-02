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
