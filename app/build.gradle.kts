import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val localProperties = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.isFile) file.inputStream().use { load(it) }
}
val backendTtsUrl = localProperties.getProperty("SPANKY_TTS_BACKEND_URL")
    ?.trim()
    ?.takeIf { it.isNotEmpty() }
    ?: "http://127.0.0.1:8000/tts"
val escapedBackendTtsUrl = backendTtsUrl.replace("\\", "\\\\").replace("\"", "\\\"")

android {
    namespace = "com.snippycalderone.spankytts"
    compileSdk = 33

    buildFeatures {
        buildConfig = true
    }

    defaultConfig {
        applicationId = "com.snippycalderone.spankytts"
        minSdk = 21
        targetSdk = 33
        versionCode = 1
        versionName = "1.0"
        buildConfigField("String", "BACKEND_TTS_URL", "\"$escapedBackendTtsUrl\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    implementation("androidx.core:core-ktx:1.10.1")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.9.0")
    implementation("org.jetbrains.kotlin:kotlin-stdlib:1.9.10")
    implementation("com.squareup.okhttp3:okhttp:4.11.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.5.1")
    implementation("androidx.datastore:datastore-preferences:1.0.0")
}
