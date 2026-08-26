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

  // LACTEVA-MOBILE-001. `extra` carries two different kinds of thing, and the
  // status code cannot tell them apart: eleven of the platform's twelve
  // `ForbiddenError` sites send a sentence, one sends a registry key. These
  // three cases pin the shape discriminator from both sides.

  test('a 403 permission KEY never overrides the sentence', () async {
    final client = ApiClient(
      inner: MockClient(
        (_) async => http.Response(
          '{"type":"https://docs.lacteva.example/errors/forbidden",'
          '"title":"forbidden","status":403,'
          '"detail":"You do not have permission to perform this action.",'
          '"extra":"pricing.ratecard.read"}',
          403,
          headers: {'content-type': 'application/json'},
        ),
      ),
    );
    try {
      await client.txStep('/v1/x', body: {});
      fail('expected ApiException');
    } on ApiException catch (e) {
      expect(e.status, 403);
      // What the operator reads on the glass — a sentence, not an identifier.
      expect(e.detail, 'You do not have permission to perform this action.');
      expect(e.detail, isNot(contains('pricing.ratecard.read')));
    }
  });

  test('a 403 SENTENCE extra still wins — the eleven sites keep their words',
      () async {
    final client = ApiClient(
      inner: MockClient(
        (_) async => http.Response(
          '{"title":"forbidden","status":403,'
          '"detail":"You do not have permission to perform this action.",'
          '"extra":"this centre is outside your assigned scope"}',
          403,
          headers: {'content-type': 'application/json'},
        ),
      ),
    );
    try {
      await client.txStep('/v1/x', body: {});
      fail('expected ApiException');
    } on ApiException catch (e) {
      // An operator standing at the wrong centre must be told WHICH thing is
      // wrong; the generic sentence would strictly lose information.
      expect(e.detail, 'this centre is outside your assigned scope');
    }
  });

  test('a 409 string extra is untouched by the key-shape rule', () async {
    final client = ApiClient(
      inner: MockClient(
        (_) async => http.Response(
          '{"title":"conflict","status":409,'
          '"detail":"The resource already exists.",'
          '"extra":"a session is already open at this centre"}',
          409,
          headers: {'content-type': 'application/json'},
        ),
      ),
    );
    try {
      await client.txStep('/v1/x', body: {});
      fail('expected ApiException');
    } on ApiException catch (e) {
      expect(e.status, 409);
      expect(e.detail, 'a session is already open at this centre');
    }
  });
}
