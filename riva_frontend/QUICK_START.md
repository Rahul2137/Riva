# RIVA - Quick Start Guide

Get RIVA running in 5 minutes! ⚡

## 1️⃣ Install Dependencies

```bash
flutter pub get
```

## 2️⃣ Create Environment File

Create a file named `.env` in the project root:

```env
API_BASE_URL=http://192.168.1.100:8000
WS_BASE_URL=ws://192.168.1.100:8000
```

**Replace `192.168.1.100` with your computer's IP address.**

### Find Your IP:
- **Windows**: `ipconfig` → Look for "IPv4 Address"
- **Mac/Linux**: `ifconfig` → Look for "inet"

## 3️⃣ Configure Firebase

1. Download `google-services.json` from Firebase Console
2. Place it in: `android/app/google-services.json`
3. Enable Google Sign-In in Firebase Console

## 4️⃣ Start Backend Server

```bash
# In your backend directory
cd riva_backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

## 5️⃣ Run RIVA

```bash
flutter run
```

## 🎉 You're Done!

1. **Sign in** with Google
2. **Tap the microphone** button
3. **Start talking** to RIVA
4. RIVA will **respond with voice**

## ⚠️ Common Issues

### "Cannot connect to WebSocket"
→ Make sure backend is running and IP address is correct in `.env`

### "Microphone permission denied"
→ Grant microphone permission when prompted

### "Google Sign-In failed"
→ Check `google-services.json` is in `android/app/`

## 📚 More Help?

- **Detailed Setup**: See [SETUP.md](SETUP.md)
- **Architecture**: See [README.md](README.md)
- **Features**: See [MVP_SUMMARY.md](MVP_SUMMARY.md)

---

**Need help?** Check the logs: `flutter logs`

