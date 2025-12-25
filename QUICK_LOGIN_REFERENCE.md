# 🚀 RIVA Login - Quick Reference

## ⚡ Quick Start (3 Steps)

### 1️⃣ Start Backend
```bash
cd riva-ml/app
python main.py
```
**Look for:** `✅ Firebase Admin SDK initialized`

### 2️⃣ Update Frontend IP
`riva_frontend/lib/config/app_config.dart`
```dart
return 'http://YOUR_IP:8000';  // e.g., http://192.168.1.7:8000
```

### 3️⃣ Run App
```bash
cd riva_frontend
flutter run
```

---

## 📂 Required Files Checklist

### Backend
- [ ] `riva-ml/app/firebase_key.json` (Firebase service account)
- [ ] `riva-ml/app/.env` (with `MONGO_URI`)
- [ ] MongoDB running (local or Atlas)

### Frontend
- [ ] `riva_frontend/android/app/google-services.json`
- [ ] API_BASE_URL configured correctly

---

## 🔍 What Changed?

### New Files
```
✨ riva-ml/app/services/auth_service.py
✨ test_login.py
✨ GOOGLE_LOGIN_SETUP.md
✨ LOGIN_FIX_SUMMARY.md
```

### Modified Files
```
📝 riva-ml/app/main.py
   - Added POST /auth/login endpoint
   - Added GET /user/profile endpoint

📝 riva-ml/requirements.txt
   - Added firebase-admin

📝 riva_frontend/lib/services/api_service.dart
   - Fixed loginUser() parameter

📝 riva_frontend/lib/providers/auth_provider.dart
   - Fixed API call
```

---

## 🧪 Quick Test

### Method 1: Use Flutter App
1. Click "Sign in with Google"
2. Check backend logs for: `✅ New user created`

### Method 2: Use Test Script
```bash
# Get token from Flutter debug logs first
python test_login.py <firebase_id_token>
```

---

## 🐛 Common Issues

| Problem | Solution |
|---------|----------|
| Can't reach backend | Use your IP, not `localhost` |
| Token verification fails | Check Firebase project matches |
| MongoDB error | Start MongoDB: `mongod` |
| Module not found | `pip install firebase-admin` |

---

## 📡 API Endpoints

### Login
```http
POST http://YOUR_IP:8000/auth/login
Content-Type: application/json

{
  "idToken": "eyJhbG..."
}
```

### Get Profile
```http
GET http://YOUR_IP:8000/user/profile
Authorization: Bearer eyJhbG...
```

---

## 💡 Testing Tips

1. **Check Backend Logs**
   - `✅` = Success
   - `❌` = Error
   - Watch for user creation messages

2. **Check Flutter Logs**
   - `Login response status: 200` = Success
   - Look for authentication errors

3. **Check MongoDB**
   ```bash
   mongo
   > use riva
   > db.users.find()
   ```

---

## 🔗 Related Docs

- Full Setup: `GOOGLE_LOGIN_SETUP.md`
- Complete Summary: `LOGIN_FIX_SUMMARY.md`
- Project Overview: `MVP_SUMMARY.md`

---

## 🎯 Authentication Flow

```
Flutter App
    ↓ (Google Sign-In)
Firebase Auth
    ↓ (ID Token)
Backend /auth/login
    ↓ (Verify Token)
MongoDB
    ↓ (User Data)
Flutter App
```

---

## ✅ Success Indicators

**Backend Console:**
```
✅ Firebase Admin SDK initialized
✅ New user created: user@example.com
```

**Flutter Console:**
```
Login response status: 200
✅ Backend login successful: {user_id: ..., email: ...}
User authenticated: user@example.com
```

**MongoDB:**
```javascript
db.users.findOne({email: "user@example.com"})
// Should return user document
```

---

**Status:** ✅ READY
**Last Updated:** Dec 25, 2025

