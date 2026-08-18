import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Claim discipline for the mobile app, as an executable check rather than
/// prose — the marketing site's claims.test.ts pattern, extended to the field
/// app (P0-PRODUCT-VISIBILITY-002).
///
/// The capability-visibility audit found ZERO overclaims in lib/ — the app's
/// honesty is structural (mock hardware is compiled out of release builds and
/// refused by the platform in production; "QR scanning arrives with device
/// integration" and "no PDF engine yet" label the future as future). This test
/// makes that honesty hold by construction: a string that asserts an
/// unavailable capability fails the suite before it ships.
///
/// Unlike the portal, the mobile app has NO labelled roadmap surface, so there
/// is no allowed home for this vocabulary at all — every pattern below is
/// banned outright. Deliberately NOT banned: "mock scale"/"mock analyzer"
/// (honest dev-only labels), the rendered supplier QR (real — only SCANNING is
/// future), "QR scanning arrives with device integration" (labelled future),
/// and comments naming the web portal (a real product).
class _Claim {
  _Claim(this.pattern, this.why);
  final RegExp pattern;
  final String why;
}

void main() {
  final claims = <_Claim>[
    // -- AI: mobile never names AI at all; the deviation flag lives (and is
    //    described) on the platform, never on this UI or the parchi.
    _Claim(RegExp(r'\bAI\b'), 'no AI exists in the product; mobile never names it'),
    _Claim(RegExp(r'machine[- ]learning', caseSensitive: false), 'no ML is deployed'),
    _Claim(RegExp(r'artificial intelligence', caseSensitive: false), 'no ML is deployed'),
    _Claim(RegExp(r'predict', caseSensitive: false), 'nothing predicts; forecasting is a roadmap item'),
    _Claim(RegExp(r'\bforecast', caseSensitive: false), 'forecasting is a V2 roadmap item, not built'),
    // -- Location: no GPS/location code or dependency exists.
    _Claim(RegExp(r'\bGPS\b'), 'no GPS exists and it is never a pilot dependency'),
    _Claim(RegExp(r'location track|geofenc', caseSensitive: false), 'no location tracking exists'),
    // -- Enterprise: reserved and not built; the field app must never imply it.
    _Claim(RegExp(r'\bSAP\b'), 'SAP/ERP integration is ENTERPRISE roadmap - no vendor, no protocol'),
    _Claim(RegExp(r'\bSSO\b|single sign-?on', caseSensitive: false), 'enterprise SSO is not built'),
    _Claim(RegExp(r'federat(ion|ed)', caseSensitive: false), 'federation/org-to-org is not built'),
    _Claim(RegExp(r'global identity', caseSensitive: false), 'global identity is not built'),
    // -- Apps that do not exist. ("customer app" is real - a household screen
    //    ships in this binary - so only the farmer app and the future WEB
    //    outlet portal are banned.)
    _Claim(RegExp(r'farmer app', caseSensitive: false), 'there is no farmer app; farmers are records who receive a parchi'),
    _Claim(RegExp(r'outlet portal', caseSensitive: false), 'the web outlet portal is a future option, not built'),
    // -- Messaging: no BSP/DLT provider is contracted; nothing sends.
    _Claim(RegExp(r'whatsapp', caseSensitive: false), 'no messaging provider is contracted; the parchi is shared as plain text'),
    _Claim(RegExp(r'(sent|delivered) (via|over|by) SMS', caseSensitive: false), 'no SMS provider is contracted'),
    // -- Hardware: capture is manual-first; mocks are dev-only and refused in
    //    production. Naming the mock honestly stays allowed; claiming a live
    //    device does not.
    _Claim(RegExp(r'automatically (reads?|captures?|weighs?|measures?)', caseSensitive: false), 'capture is manual; automated read-assist is discovery-gated roadmap'),
    _Claim(RegExp(r'(scale|analyzer) (is )?(connected|integrated|online)', caseSensitive: false), 'no device integration is shipped'),
    _Claim(RegExp(r'reads? the (scale|analyzer)', caseSensitive: false), 'no device integration is shipped'),
    _Claim(RegExp(r'\bIoT\b', caseSensitive: false), 'no IoT capability exists'),
    // -- QR: rendering the supplier QR is real; scanning one is future.
    _Claim(RegExp(r'scan (a|the|your) (QR|code|barcode)|tap to scan', caseSensitive: false), 'QR scanning is not built; only rendering a QR is real'),
    // -- Government / compliance: documents, not integrations; no attestations.
    _Claim(RegExp(r'government (integration|portal|filing|approved)', caseSensitive: false), 'no government integration exists'),
    _Claim(RegExp(r'SOC ?2|ISO[- ]?(?!8601|4217)\d{4,5}|GDPR|HIPAA|PCI[- ]DSS', caseSensitive: false), 'no certifications or compliance attestations exist to claim (ISO 8601 dates and ISO 4217 currency codes are factual standards, not attestations)'),
    _Claim(RegExp(r'(legally|fully) compliant|100% secure', caseSensitive: false), 'no compliance or absolute-security claims'),
  ];

  final files = Directory('lib')
      .listSync(recursive: true)
      .whereType<File>()
      .where((f) => f.path.endsWith('.dart'))
      .toList();

  test('finds the source tree', () {
    expect(files.length, greaterThan(10));
  });

  for (final claim in claims) {
    test('never says ${claim.pattern.pattern} (${claim.why})', () {
      final offenders = <String>[
        for (final file in files)
          if (claim.pattern.hasMatch(file.readAsStringSync())) file.path,
      ];
      expect(offenders, isEmpty,
          reason: 'overclaim "${claim.pattern.pattern}" found in: '
              '${offenders.join(", ")} - ${claim.why}');
    });
  }
}
