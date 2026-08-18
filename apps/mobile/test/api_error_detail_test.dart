/// P0-PILOT-004: the platform localizes `detail` and often carries the
/// specific, actionable reason as a plain STRING in `extra`. The first
/// physical handset showed an operator "The resource already exists."
/// where the truth was "supplier is not assigned to this collection
/// center". The client now surfaces the string extra as the detail.
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lacteva_mobile/src/api.dart';

void main() {
  test('a string `extra` becomes the shown detail', () async {
    final client = ApiClient(
      inner: MockClient(
        (_) async => http.Response(
          '{"title":"conflict","status":409,'
          '"detail":"The resource already exists.",'
          '"extra":"supplier is not assigned to this collection center"}',
          409,
          headers: {'content-type': 'application/json'},
        ),
      ),
    );
    try {
      await client.txStep('/v1/milk-transactions/x/identify', body: {});
      fail('expected ApiException');
    } on ApiException catch (e) {
      expect(e.status, 409);
      expect(e.detail, 'supplier is not assigned to this collection center');
    }
  });

  test('UTF-8 in an error body survives a missing charset header', () async {
    final client = ApiClient(
      inner: MockClient(
        (_) async => http.Response.bytes(
          utf8.encode(
            '{"detail":"mock_scale is not permitted \u2014 capture a real reading",'
            '"extra":"\u0917\u093e\u092f"}',
          ),
          403,
          headers: {'content-type': 'application/json'}, // no charset — the field case
        ),
      ),
    );
    try {
      await client.txStep('/v1/x', body: {});
      fail('expected ApiException');
    } on ApiException catch (e) {
      expect(e.detail, 'गाय'); // the string extra, intact Devanagari
    }
  });

  test('a map `extra` keeps the detail and stays structured', () async {
    final client = ApiClient(
      inner: MockClient(
        (_) async => http.Response(
          '{"detail":"pricing failed","extra":{"stage":"product"}}',
          409,
          headers: {'content-type': 'application/json'},
        ),
      ),
    );
    try {
      await client.txStep('/v1/x', body: {});
      fail('expected ApiException');
    } on ApiException catch (e) {
      expect(e.detail, 'pricing failed');
      expect(e.extra, {'stage': 'product'});
    }
  });
}
