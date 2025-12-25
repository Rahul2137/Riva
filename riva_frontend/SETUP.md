# RIVA Frontend - Setup Guide

This guide will help you get RIVA up and running quickly.

## ✅ Prerequisites Checklist

Before you begin, ensure you have:

- [ ] Flutter SDK installed (3.7.2 or higher)
- [ ] Android Studio or VS Code with Flutter extensions
- [ ] A Firebase project created
- [ ] RIVA backend server code
- [ ] Git installed

## 📋 Step-by-Step Setup

### 1. Clone the Repository

```bash
git clone <your-repository-url>
cd riva_frontend
```

### 2. Install Dependencies

```bash
flutter pub get
```

### 3. Configure Firebase

#### A. Create Firebase Project
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Create a new project or select existing
3. Enable Google Sign-In in Authentication > Sign-in method

#### B. Add Android Configuration
1. In Firebase Console, add an Android app
2. Download `google-services.json`
3. Place it in: `android/app/google-services.json`
4. Update `android/app/build.gradle.kts` if needed

#### C. Add iOS Configuration (if building for iOS)
1. In Firebase Console, add an iOS app
2. Download `GoogleService-Info.plist`
3. Place it in: `ios/Runner/GoogleService-Info.plist`

### 4. Configure Backend URL

Create a `.env` file in the project root:

```env
API_BASE_URL=http://YOUR_IP_ADDRESS:8000
WS_BASE_URL=ws://YOUR_IP_ADDRESS:8000
```

**Important**: Replace `YOUR_IP_ADDRESS` with:
- Your computer's local IP for testing on physical device
- `localhost` for emulator/simulator
- Your server IP for production

**Example for local development:**
```env
API_BASE_URL=http://192.168.1.100:8000
WS_BASE_URL=ws://192.168.1.100:8000
```

### 5. Start Backend Server

Make sure your RIVA backend is running:

```bash
# In your backend directory
cd riva_backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 6. Run the App

```bash
flutter run
```

Or select your device in IDE and click Run.

## 🔧 Common Issues & Solutions

### Issue: "Failed to connect to WebSocket"

**Solutions:**
1. Verify backend is running: `curl http://YOUR_IP:8000/health`
2. Check firewall settings (allow port 8000)
3. Ensure you're using the correct IP address
4. For Android physical device, ensure phone and computer are on same network

### Issue: "Microphone permission denied"

**Android:**
1. Check `android/app/src/main/AndroidManifest.xml` has:
   ```xml
   <uses-permission android:name="android.permission.RECORD_AUDIO"/>
   <uses-permission android:name="android.permission.INTERNET"/>
   ```

**iOS:**
1. Check `ios/Runner/Info.plist` has:
   ```xml
   <key>NSMicrophoneUsageDescription</key>
   <string>RIVA needs microphone access for voice interaction</string>
   ```

### Issue: "Google Sign-In failed"

**Solutions:**
1. Verify `google-services.json` is in correct location
2. Check SHA-1 certificate is added to Firebase (for Android)
3. Ensure Google Sign-In is enabled in Firebase Console
4. For iOS, ensure URL schemes are configured

### Issue: "Developer Mode not enabled" (Windows)

This warning appears on Windows. To enable:
1. Run `start ms-settings:developers`
2. Enable "Developer Mode"
3. Restart Android Studio/VS Code

## 🎯 Testing the Setup

### 1. Test Authentication
- Launch app
- Click "Sign in with Google"
- Verify successful login

### 2. Test Voice System
- Tap microphone button on home screen
- Speak: "Hello RIVA"
- Verify RIVA responds

### 3. Test Conversation History
- Navigate to "Chat" tab
- Verify previous messages appear

## 📱 Building for Production

### Android APK
```bash
flutter build apk --release
```

APK will be in: `build/app/outputs/flutter-apk/app-release.apk`

### Android App Bundle (for Play Store)
```bash
flutter build appbundle --release
```

### iOS
```bash
flutter build ios --release
```

## 🔐 Environment Variables

Create `.env` file with these variables:

| Variable | Description | Example |
|----------|-------------|---------|
| API_BASE_URL | Backend HTTP endpoint | http://192.168.1.100:8000 |
| WS_BASE_URL | Backend WebSocket endpoint | ws://192.168.1.100:8000 |

## 📦 Project Structure

```
riva_frontend/
├── lib/
│   ├── main.dart              # App entry
│   ├── config/                # Configuration
│   ├── core/                  # Core utilities
│   ├── models/                # Data models
│   ├── providers/             # State management
│   ├── services/              # Business logic
│   ├── screens/               # UI screens
│   └── widgets/               # Reusable widgets
├── android/                   # Android specific
├── ios/                       # iOS specific
├── assets/                    # Images, fonts, etc.
├── .env                       # Environment config (create this)
└── pubspec.yaml              # Dependencies
```

## 🐛 Debug Mode

To run with detailed logs:

```bash
flutter run --debug --verbose
```

Check logs for:
- WebSocket connection status
- Audio streaming info
- Auth token validation

## 🚀 Next Steps

After successful setup:

1. **Test all features**: Voice, Auth, Conversation history
2. **Configure backend endpoints**: Calendar API, Finance API
3. **Customize theme**: Update `lib/core/theme.dart`
4. **Add features**: Extend providers and services

## 📞 Need Help?

- Check the main [README.md](README.md) for architecture details
- Review error logs: `flutter logs`
- Check backend logs for API issues

## ✨ You're Ready!

If everything works:
- ✅ App launches successfully
- ✅ You can sign in with Google
- ✅ Voice button appears on home screen
- ✅ RIVA responds to your voice

**You're all set! Start talking to RIVA! 🎉**

