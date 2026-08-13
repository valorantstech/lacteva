import java.util.Properties

// PORTAL-001 / F-05: the release keystore, supplied at build time.
//
// `android/key.properties` is gitignored and never committed. CI writes it
// from secrets immediately before the build and deletes it after; a developer
// building a signed APK locally writes their own. Its absence is not an
// error here — it is an error only if someone then asks for a RELEASE build,
// which is what the task-graph check at the bottom of this file enforces.
val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties().apply {
    if (keystorePropertiesFile.exists()) {
        keystorePropertiesFile.inputStream().use { load(it) }
    }
}
val hasReleaseKeystore = keystoreProperties.getProperty("storeFile") != null

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.lacteva.lacteva_mobile"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.lacteva.lacteva_mobile"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (hasReleaseKeystore) {
            create("release") {
                storeFile = file(keystoreProperties.getProperty("storeFile"))
                storePassword = keystoreProperties.getProperty("storePassword")
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            // PORTAL-001 / F-05.
            //
            // This used to read `signingConfig = signingConfigs.getByName("debug")`
            // with a TODO above it, which meant every release build was signed
            // with the publicly-known Android debug key: not distributable, not
            // upgradeable, and indistinguishable from a build anyone could have
            // made. FINAL-001 rated it a blocker.
            //
            // A release build now FAILS rather than falling back. A fallback is
            // how a debug-signed APK reaches a farmer's phone — the build goes
            // green, nobody reads the warning, and the mistake is only visible
            // months later when the upgrade is rejected.
            //
            // DEMO-012: the check itself used to live HERE, and this block is
            // CONFIGURATION, which Gradle evaluates for every invocation. So it
            // threw on `assembleDebug` too — on a machine with no release
            // keystore, which is every developer's machine and every CI job that
            // only runs tests, the app could not be built at all. The guard now
            // fires from the task graph, where it can tell what was actually
            // asked for. Leaving `signingConfig` null here is safe precisely
            // because that guard stops a release before it can execute unsigned.
            signingConfig = signingConfigs.findByName("release")
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }
}

flutter {
    source = "../.."
}

// PORTAL-001 / F-05, moved here by DEMO-012.
//
// The task graph is the only place that knows what was actually REQUESTED. A
// check in `buildTypes.release { }` runs while Gradle configures the project,
// which it does identically for `assembleDebug`, `test` and `assembleRelease` —
// so the guard refused every build rather than release builds. Here it can tell
// the difference, and it still refuses to let an unsigned release run.
gradle.taskGraph.whenReady {
    if (hasReleaseKeystore) return@whenReady
    val releaseTask = allTasks.firstOrNull { task ->
        task.project == project &&
            Regex("^(assemble|bundle|package)Release$").matches(task.name)
    } ?: return@whenReady
    throw GradleException(
        "Release build requested (${releaseTask.name}) with no signing configuration.\n" +
        "Create android/key.properties from android/key.properties.example " +
        "and point storeFile at the release keystore.\n" +
        "See DEPLOYMENT.md - Mobile release builds.\n" +
        "Debug signing is NEVER used for a release build."
    )
}
