# mobile

Lacteva Flutter application — the future home of Lacteva Collect's operator experience (shift control, member check-in, collection recording per `docs/13-products/lacteva-collect/`). Currently ships the SPRINT-001 bootstrap: a platform-status screen polling `platform-core`'s readiness endpoint.

Scaffolded with `flutter create` (org `com.lacteva`, project `lacteva_mobile`, platforms android/ios/web), Flutter 3.38 stable.

## Run

```bash
flutter devices                                            # list targets
flutter run --dart-define=LACTEVA_API_URL=http://10.0.2.2:8000   # Android emulator
flutter run -d chrome --dart-define=LACTEVA_API_URL=http://localhost:8000
# or from the repo root: make mobile [DEVICE=<id>]
```

`10.0.2.2` is the Android emulator's route to the host machine. The API URL is a compile-time define (`lib/main.dart`), defaulting to `http://localhost:8000`.

## Quality gates (CI-enforced)

```bash
flutter analyze
flutter test
```

## Architecture constraints before feature work (from the Collect package)

- **Offline-first** (rule R09): the local queue + sync engine is the first M2 infrastructure slice — features must not assume connectivity.
- **Localization from day one**: `flutter_localizations` + ARB files (en/sw/hi to start), matching platform i18n.
- Auth against platform-core (`/v1/auth/token` + refresh), tenant-scoped.
- Hardware integration (scales/analyzers per PSP-0007) goes behind a device-profile platform-channel interface — M2+.
