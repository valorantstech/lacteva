import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/main.dart';

void main() {
  testWidgets('bootstrap screen renders', (tester) async {
    await tester.pumpWidget(const LactevaApp());
    expect(find.text('Lacteva — Platform Status'), findsOneWidget);
    expect(find.text('platform-core'), findsOneWidget);
  });
}
