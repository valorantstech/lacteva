# PORTAL-001 / F-05. Flutter's engine is reached by reflection from the
# platform side, so it must survive shrinking. Everything else is Dart, which
# is AOT-compiled and untouched by R8.
-keep class io.flutter.** { *; }
-keep class io.flutter.plugins.** { *; }
