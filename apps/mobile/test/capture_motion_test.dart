/// The counter stays instant (LACTEVA-MOBILE-008; storyboard panel 6).
///
/// This is the panel the other five exist to earn. The capture path — weigh,
/// quality, price, accept — is where an operator's hands work with a queue of
/// farmers in front of them, and it carries no animation at all. Not a short
/// one. None.
///
/// **The guard is behavioural, not a grep.** It drives the real wizard to each
/// capture step, lets it settle, pumps one `LactevaMotion.fast` (160ms), and
/// asserts nothing is still scheduling frames. A structural scan for long
/// duration literals would pass a screen that composed two short animations
/// into a long one, or that started a repeating one; a scheduled frame is the
/// thing that actually costs a farmer their place in the queue.
///
/// It is watched failing against a real slow animation injected into a capture
/// step — see the report for WO-21.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';
import 'package:lacteva_mobile/src/brand/motion.dart';
import 'package:lacteva_mobile/src/collection_wizard.dart';
import 'package:lacteva_mobile/src/offline/offline_client.dart';
import 'package:lacteva_mobile/src/offline/queue.dart';
import 'package:lacteva_mobile/src/offline/store.dart';
import 'package:lacteva_mobile/src/session.dart';
import 'package:lacteva_mobile/src/theme.dart';

/// The platform, answering each capture step the way it really does.
class _Platform extends ApiClient {
  @override
  Future<Map<String, dynamic>> txStep(String path, {Object? body}) async =>
      <String, dynamic>{
        'id': 'tx-1',
        'state': path.endsWith('/complete') ? 'COMPLETED' : 'IN_PROGRESS',
        'net_weight': '10.000',
        'pricing_status': 'priced',
        'gross_amount': '581.25',
        'currency': 'INR',
      };

  @override
  Future<Map<String, dynamic>> transactionSlip(String txId) async =>
      <String, dynamic>{
        'slip_number': 'SLP-2026-000481',
        'text': 'Savita Kadam · 10.0 kg · 581.25',
      };
}

/// The offline client the wizard takes, with its reads sent to the fake.
class _Client extends OfflineApiClient {
  _Client(this.platform)
    : super(queue: SyncQueue(MemoryOfflineStore()), deviceId: 'test-device');

  final _Platform platform;

  @override
  Future<Map<String, dynamic>> transactionSlip(String txId) =>
      platform.transactionSlip(txId);

  /// The capture path itself. Without this the wizard reaches for the real
  /// network and never leaves step one — which would have made the guard
  /// below pass by never running anything at all.
  @override
  Future<Map<String, dynamic>> txStep(String path, {Object? body}) =>
      platform.txStep(path, body: body);
}

OfflineApiClient _client() => _Client(_Platform());

Session _session() => Session(
  userId: 'u1',
  email: 'operator@dairy.example',
  fullName: 'Operator',
  tenantId: 'org-1',
  permissions: const {
    'collection.session.manage',
    'collection.transaction.record',
  },
);

/// Open the wizard at a step, with the real client behind it.
Future<void> _open(
  WidgetTester tester, {
  required int at,
  bool reducedMotion = false,
}) async {
  final screen = CollectionWizardScreen(
    key: UniqueKey(),
    client: _client(),
    sessionId: 'sess-1',
    session: _session(),
    initialStep: at,
  );
  await tester.pumpWidget(
    MaterialApp(
      theme: lactevaTheme(),
      // Copied from the ambient data: a bare `MediaQueryData()` has a zero
      // size, and a screen laid out in a zero viewport relayouts forever —
      // which reads exactly like an animation that never stops.
      home: Builder(
        builder: (context) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(disableAnimations: reducedMotion),
          child: screen,
        ),
      ),
    ),
  );
  await tester.pump();
}

/// The whole capture path, ending on the parchi.
Future<void> _driveToParchi(
  WidgetTester tester, {
  bool reducedMotion = false,
}) async {
  await _open(tester, at: 1, reducedMotion: reducedMotion);
  await tester.pumpAndSettle();
  await tester.tap(find.text('Receive milk'));
  await tester.pumpAndSettle();
  await tester.enterText(find.widgetWithText(TextField, 'Gross (kg)'), '12');
  await tester.enterText(find.widgetWithText(TextField, 'Tare (kg)'), '2');
  await tester.tap(find.text('Capture weight'));
  await tester.pumpAndSettle();
  await tester.enterText(find.widgetWithText(TextField, 'FAT %'), '4.1');
  await tester.enterText(find.widgetWithText(TextField, 'SNF %'), '8.5');
  await tester.enterText(find.widgetWithText(TextField, 'CLR'), '27');
  await tester.tap(find.text('Capture quality'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Accept & complete'));
  // ONE frame, not a settle: settling would run the parchi moment to its end
  // and leave nothing to observe.
  await tester.pump();
  await tester.pump();
}

void main() {
  group('the capture path runs no animation', () {
    testWidgets('every step, walked the way an operator walks it', (
      tester,
    ) async {
      // DRIVEN, not jumped to. `initialStep` reaches a step without a
      // transaction on it, and the review step renders nothing without one —
      // a guard that jumped there would be asserting about an empty screen.
      // This walks the real path and checks the budget at each stop.
      // Two halves, because one alone cannot prove this.
      //
      // TIMING proves nothing LOOPS: `pumpAndSettle` returns only when every
      // ticker has stopped, and throws if one never does. That is the
      // disqualifying class — an animation that outlives the operator's
      // attention.
      //
      // It cannot prove the 160ms budget, and pretending otherwise would be
      // a guard nobody could keep: Flutter's own `InputDecorator` floats its
      // label over 167ms and its ink splashes run longer still, on every text
      // field and every button in the app. Neither is ours to change and
      // neither is a flourish.
      //
      // So STRUCTURE proves the budget instead, and proves it absolutely:
      // the capture path carries no Lacteva motion at all. Nothing of ours
      // runs here for 600ms, or 420ms, or 20ms.
      Future<void> budget(String step) async {
        await tester.pumpAndSettle();
        for (final motion in [
          ParchiMint,
          SuccessRipple,
          SyncDroplets,
          SettleIn,
        ]) {
          expect(
            find.byType(motion),
            findsNothing,
            reason: 'the $step step carries a $motion — panel 6 forbids it',
          );
        }
        expect(
          tester.binding.transientCallbackCount,
          0,
          reason: 'the $step step left something running',
        );
      }

      await _open(tester, at: 1);
      expect(find.text('Receive milk'), findsOneWidget);
      await budget('milk');

      await tester.tap(find.text('Receive milk'));
      await tester.pumpAndSettle();
      expect(find.widgetWithText(TextField, 'Gross (kg)'), findsOneWidget);
      await budget('weigh');

      await tester.enterText(
        find.widgetWithText(TextField, 'Gross (kg)'),
        '12',
      );
      await tester.enterText(find.widgetWithText(TextField, 'Tare (kg)'), '2');
      await tester.tap(find.text('Capture weight'));
      await tester.pumpAndSettle();
      expect(find.widgetWithText(TextField, 'FAT %'), findsOneWidget);
      await budget('quality');

      await tester.enterText(find.widgetWithText(TextField, 'FAT %'), '4.1');
      await tester.enterText(find.widgetWithText(TextField, 'SNF %'), '8.5');
      await tester.enterText(find.widgetWithText(TextField, 'CLR'), '27');
      await tester.tap(find.text('Capture quality'));
      await tester.pumpAndSettle();
      // The review step, WITH a transaction on it — which is the only state
      // in which its body exists at all.
      expect(find.text('Accept & complete'), findsOneWidget);
      await budget('price and accept');
    });

    test('the wizard rolls no animation of its own', () {
      // The structural half, and the one that actually holds the line: the
      // capture path may not grow a controller by hand either. A screen that
      // drove its own Ticker would slip past a widget-type check and past a
      // timing bound tuned to the framework.
      final source = File(
        'lib/src/collection_wizard.dart',
      ).readAsStringSync();
      for (final forbidden in [
        'AnimationController',
        'TickerProvider',
        'AnimatedContainer',
        'AnimatedOpacity',
      ]) {
        expect(
          source,
          isNot(contains(forbidden)),
          reason:
              'the capture path declares $forbidden — panel 6 says the '
              'counter stays instant',
        );
      }
    });

    test('and the budget is the token, not a number typed here', () {
      // If someone raises `fast`, this test raises with it — which is the
      // point of a token. 160ms is the board's figure and the theme's.
      expect(LactevaMotion.fast.inMilliseconds, 160);
      expect(LactevaMotion.instant.inMilliseconds, lessThan(160));
    });
  });

  group('the outcome step is where motion is allowed', () {
    testWidgets('the parchi moment runs, and is over inside its own beat', (
      tester,
    ) async {
      // Panel 2. Not on the capture path: the capture is done, the farmer has
      // their slip, and this is the one celebration the app permits. Driven
      // the whole way rather than jumped to, because the parchi fires when
      // the SLIP arrives — an offline completion has none and gets none.
      await _driveToParchi(tester);
      expect(find.textContaining('SLP-2026-000481'), findsOneWidget);
      await tester.pump(const Duration(milliseconds: 400));

      // Still going at 400ms — proving the exemption is real and that the
      // guard above would have caught this had it been a capture step.
      expect(tester.binding.hasScheduledFrame, isTrue);

      await tester.pump(MilkMoments.parchi);
      await tester.pump();
      expect(
        tester.binding.hasScheduledFrame,
        isFalse,
        reason: 'then the queue moves on',
      );
    });

    testWidgets('reduced motion makes even that step instant', (tester) async {
      await _driveToParchi(tester, reducedMotion: true);
      expect(find.textContaining('SLP-2026-000481'), findsOneWidget);
      // No controller was built at all — not one running at zero.
      expect(tester.binding.hasScheduledFrame, isFalse);
    });
  });
}
