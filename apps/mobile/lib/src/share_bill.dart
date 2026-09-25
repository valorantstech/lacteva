/// Handing a document to the phone's share sheet (WO-83 §2).
///
/// The bytes are the platform's PDF; this file only puts them somewhere the
/// share sheet can read and opens it. Kept apart from the screen so a widget
/// test can hand in a recorder instead of the real sheet.
library;

import 'dart:io';
import 'dart:typed_data';

import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

/// What the bill screen calls once it has the bytes.
typedef ShareDocument = Future<void> Function(Uint8List bytes, String filename);

/// Writes the document to the app's cache and opens the share sheet on it —
/// "Save to Files", a messaging app, print, whatever the phone offers.
Future<void> shareDocument(Uint8List bytes, String filename) async {
  final dir = await getTemporaryDirectory();
  final file = File('${dir.path}/$filename');
  await file.writeAsBytes(bytes, flush: true);
  await SharePlus.instance.share(
    ShareParams(files: [XFile(file.path, mimeType: 'application/pdf')]),
  );
}
