# RIVA Frontend

**RIVA** - Your AI Personal Assistant

A voice-first, AI personal assistant designed to fully replace a human personal assistant. RIVA is proactive, autonomous, and works across productivity, finance, planning, and daily decisions.

## 🌟 Features

### Current (MVP)
- ✅ **Voice Interaction**: Full-duplex real-time voice assistant
- ✅ **Google Authentication**: Secure Firebase authentication
- ✅ **Conversation History**: Local storage of all interactions
- ✅ **Interrupt Capability**: Stop RIVA mid-speech
- ✅ **Real-time Transcription**: See what you say and what RIVA responds
- ✅ **Modern UI**: Beautiful, minimal interface with animations
- ✅ **State Management**: Clean Provider architecture

### Coming Soon
- 📅 Google Calendar Integration
- 💰 Finance Tracking (expenses, income, budgets)
- ✅ Task & Reminder Management
- 🤖 Multi-agent Architecture
- 🧠 Proactive Suggestions

## 🏗️ Architecture

```
lib/
├── main.dart                    # App entry point
├── config/
│   └── app_config.dart          # Configuration management
├── core/
│   └── theme.dart               # App theming
├── models/
│   ├── message_model.dart       # Message data structure
│   ├── conversation_model.dart  # Conversation data
│   └── voice_state_model.dart   # Voice system state
├── providers/
│   ├── auth_provider.dart       # Authentication state
│   ├── voice_provider.dart      # Voice interaction state
│   └── conversation_provider.dart # Conversation management
├── services/
│   ├── auth_service.dart        # Firebase auth logic
│   ├── api_service.dart         # Backend API calls
│   ├── voice_service.dart       # WebSocket + audio handling
│   └── storage_service.dart     # Local data persistence
├── screens/
│   ├── login_screen.dart        # Google Sign-In
│   ├── main_layout.dart         # Bottom navigation
│   ├── home_screen.dart         # Voice interface
│   ├── conversation_screen.dart # Chat history
│   ├── productivity_screen.dart # Tasks (placeholder)
│   ├── finance_screen.dart      # Finance (placeholder)
│   └── settings_screen.dart     # Settings & profile
└── widgets/
    ├── voice_visualizer.dart    # Animated mic button
    ├── message_bubble.dart      # Chat message UI
    └── status_indicator.dart    # Connection status
```

## 🚀 Getting Started

### Prerequisites
- Flutter SDK (>=3.7.2)
- Firebase project with Google Sign-In enabled
- Backend server running (FastAPI)

### Setup

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd riva_frontend
   ```

2. **Install dependencies**
   ```bash
   flutter pub get
   ```

3. **Configure Firebase**
   - Add your `google-services.json` (Android) to `android/app/`
   - Add your `GoogleService-Info.plist` (iOS) to `ios/Runner/`

4. **Configure Backend URL**
   
   Create a `.env` file in the root directory:
   ```env
   API_BASE_URL=http://YOUR_BACKEND_IP:8000
   WS_BASE_URL=ws://YOUR_BACKEND_IP:8000
   ```
   
   Or use the default localhost configuration.

5. **Run the app**
   ```bash
   flutter run
   ```

## 🔧 Configuration

### Backend URLs
Update the backend URLs in `.env` file or directly in `lib/config/app_config.dart`:
- `API_BASE_URL`: HTTP endpoint for REST API
- `WS_BASE_URL`: WebSocket endpoint for voice streaming

### Firebase
Ensure your Firebase project has:
- Google Sign-In enabled in Authentication
- Proper Android/iOS configuration

## 📱 Usage

1. **Sign In**: Use Google Sign-In on the login screen
2. **Voice Interaction**: 
   - Tap the microphone button on the home screen
   - Start speaking
   - RIVA will respond with voice and text
   - Tap "Interrupt" to stop RIVA mid-speech
3. **View History**: Check the Conversation tab for full transcript
4. **Settings**: Manage your profile and clear data

## 🎯 Voice Commands (Examples)

Try these with RIVA:
- "Schedule a meeting tomorrow at 3 PM"
- "What's on my calendar today?"
- "Add a reminder to call John"
- "Log an expense of $50 for groceries"
- "What did I spend this month?"

## 🛠️ Tech Stack

- **Framework**: Flutter 3.7+
- **State Management**: Provider
- **Authentication**: Firebase Auth + Google Sign-In
- **Voice**: flutter_sound + flutter_tts
- **Networking**: WebSockets (web_socket_channel)
- **Storage**: SharedPreferences
- **UI**: Material Design 3 + Google Fonts

## 📦 Key Dependencies

```yaml
flutter_sound: ^9.28.0        # Audio recording
flutter_tts: ^4.2.2           # Text-to-speech
web_socket_channel: ^3.0.3    # Real-time communication
firebase_auth: ^5.5.4         # Authentication
google_sign_in: ^6.2.1        # Google OAuth
provider: ^6.1.1              # State management
shared_preferences: ^2.2.2    # Local storage
```

## 🐛 Troubleshooting

### WebSocket Connection Issues
- Ensure backend server is running
- Check firewall settings
- Verify the correct IP address in `.env`

### Microphone Permission
- Android: Check `AndroidManifest.xml` has microphone permission
- iOS: Check `Info.plist` has microphone usage description

### Firebase Auth Issues
- Verify `google-services.json` / `GoogleService-Info.plist` are correct
- Check Firebase console for enabled authentication methods

## 🔮 Roadmap

### Phase 1: MVP ✅
- Voice interaction
- Authentication
- Conversation history

### Phase 2: Core Features (In Progress)
- Google Calendar integration
- Finance tracking
- Task management

### Phase 3: Intelligence
- Multi-agent architecture
- Proactive suggestions
- Long-term memory
- Context awareness

### Phase 4: Scale
- Custom ML models
- Multi-platform (web, desktop)
- Team features
- API for third-party integrations

## 📄 License

Proprietary - All rights reserved

## 👥 Team

Built with vision to create the ultimate AI personal assistant.

---

**RIVA** - *Get things done, the intelligent way.*
