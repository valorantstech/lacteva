// WO-100: a reset code pasted with its surroundings is still the code.
import 'package:flutter_test/flutter_test.dart';
import 'package:lacteva_mobile/src/api.dart';

void main() {
  const token = 'abcXYZ_-09abcXYZ_-09abcXYZ_-09abcXYZ_-09';
  test('keeps the token and nothing else', () {
    for (final pasted in [
      '$token.',
      '"$token"',
      'code: $token\n',
      ' $token \r\n',
      'https://app.lacteva.com/reset-password#code=$token',
    ]) {
      expect(normaliseToken(pasted), token, reason: pasted);
    }
    expect(normaliseToken(''), '');
    expect(normaliseToken('...'), '');
  });
}
