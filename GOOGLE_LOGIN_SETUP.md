# Google Login Setup Guide for RIVA

## Overview
This guide explains how to set up and test the Google login flow between your Flutter frontend and FastAPI backend.

## Architecture

```
Flutter App (Firebase Auth)
    ↓ Google Sign-In
    ↓ Get ID Token
    ↓ POST /auth/login {idToken}
FastAPI Backend (Firebase Admin SDK)
    ↓ Verify Token
    ↓ Create/Update User in MongoDB
    ↓ Return User Data
```

## Prerequisites

### 1. Firebase Setup
- Firebase project created at https://console.firebase.google.com
- Google Sign-In enabled in Firebase Authentication
- `google-services.json` in `riva_frontend/android/app/`
- `firebase_key.json` (service account) in `riva-ml/app/`

### 2. Backend Requirements

**Install dependencies:**
```bash
cd riva-ml
pip install -r requirements.txt
```

**Environment Variables** (create `.env` in `riva-ml/app/`):
```env
MONGO_URI=mongodb://localhost:27017
# or your MongoDB Atlas connection string
# MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/
```

### 3. Frontend Requirements

**Environment Variables** (create `.env` in `riva_frontend/`):
```env
API_BASE_URL=http://YOUR_IP:8000
WS_BASE_URL=ws://YOUR_IP:8000
```

**Note:** Replace `YOUR_IP` with your computer's local IP address (not localhost for mobile testing)

## Backend Changes Made

### 1. Created `services/auth_service.py`
- Initializes Firebase Admin SDK
- `verify_firebase_token()` - Verifies ID tokens from Flutter
- `create_or_update_user()` - Creates/updates user in MongoDB
- `get_user_by_id()` - Retrieves user data

### 2. Updated `main.py`
- Added `POST /auth/login` endpoint for Firebase authentication
- Added `GET /user/profile` endpoint to fetch user data
- Updated CORS to allow all origins (for mobile app)
- Added Pydantic models for request/response validation

### 3. Updated `requirements.txt`
- Added `firebase-admin==6.6.0`

## Frontend Changes Made

### 1. Updated `services/api_service.dart`
- `loginUser()` now accepts ID token string instead of object
- Better error handling and logging
- Parses success/failure from backend response

### 2. Updated `providers/auth_provider.dart`
- Calls `ApiService.loginUser(idToken)` with correct parameters
- Gracefully handles backend failures (allows offline mode)
- Logs backend response for debugging

## Testing the Login Flow

### Step 1: Start MongoDB
```bash
# If using local MongoDB
mongod

# Check if running
mongo
```

### Step 2: Start Backend
```bash
cd riva-ml/app
python main.py
```

You should see:
```
✅ Firebase Admin SDK initialized
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 3: Start Flutter App
```bash
cd riva_frontend
flutter run
```

### Step 4: Test Login
1. Click "Sign in with Google"
2. Select your Google account
3. Check backend console for:
```
✅ New user created: user@example.com
```
4. Check Flutter logs for:
```
Login response status: 200
✅ Backend login successful: {user_id: ..., email: ...}
User authenticated: user@example.com
```

## Troubleshooting

### Backend Issues

**Error: "Firebase Admin SDK initialization failed"**
- Ensure `firebase_key.json` exists in `riva-ml/app/`
- Verify it's a valid service account key file

**Error: "Invalid authentication token"**
- Check that Firebase project IDs match between Flutter and backend
- Verify `google-services.json` is from the same Firebase project

**Error: "Database error"**
- Ensure MongoDB is running
- Check `MONGO_URI` in `.env` file
- Verify network connectivity to MongoDB

### Frontend Issues

**Error: "Login error: SocketException"**
- Verify backend is running on the specified IP and port
- Check `API_BASE_URL` in frontend `.env`
- Ensure phone/emulator can reach the backend IP
- Test with: `curl http://YOUR_IP:8000/docs`

**Error: "Google Sign-In cancelled"**
- User cancelled the sign-in flow
- Try again

**Error: "Failed to get authentication token"**
- Firebase authentication succeeded but couldn't get ID token
- Check Firebase console for user creation
- Try signing out and back in

## Database Structure

### Users Collection
```json
{
  "user_id": "firebase_uid",
  "email": "user@example.com",
  "name": "John Doe",
  "picture": "https://...",
  "created_at": "2025-12-25T...",
  "last_login": "2025-12-25T...",
  "timezone": "UTC"
}
```

## API Endpoints

### POST /auth/login
**Request:**
```json
{
  "idToken": "eyJhbGciOiJSUzI1NiIsImtpZCI6..."
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Login successful",
  "user": {
    "user_id": "abc123",
    "email": "user@example.com",
    "name": "John Doe",
    "picture": "https://...",
    "is_new_user": true
  }
}
```

**Response (Error):**
```json
{
  "detail": "Invalid authentication token"
}
```

### GET /user/profile
**Headers:**
```
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...
```

**Response:**
```json
{
  "success": true,
  "user": {
    "user_id": "abc123",
    "email": "user@example.com",
    "name": "John Doe",
    "picture": "https://...",
    "created_at": "2025-12-25T...",
    "last_login": "2025-12-25T...",
    "timezone": "UTC"
  }
}
```

## Security Notes

1. **ID Token Verification**: Backend verifies Firebase ID tokens using Firebase Admin SDK
2. **CORS**: Currently set to allow all origins for development. Update for production:
   ```python
   allow_origins=["https://your-domain.com"]
   ```
3. **HTTPS**: Use HTTPS in production for secure token transmission
4. **Token Expiry**: Firebase ID tokens expire after 1 hour. Frontend should handle refresh automatically

## Next Steps

After successful login:
1. Implement protected API endpoints that require authentication
2. Add token refresh logic for long sessions
3. Implement user profile management
4. Add user preferences and settings storage
5. Integrate with productivity and finance modules

## Common Patterns

### Making Authenticated API Calls (Frontend)
```dart
final token = await authProvider.authToken;
final response = await http.get(
  Uri.parse('$baseUrl/some-endpoint'),
  headers: {
    "Authorization": "Bearer $token",
  },
);
```

### Protecting Endpoints (Backend)
```python
from services.auth_service import verify_firebase_token

@app.get("/protected-endpoint")
async def protected_route(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = auth_header.split("Bearer ")[1]
    decoded = await verify_firebase_token(token)
    
    if not decoded:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user_id = decoded.get("uid")
    # ... proceed with authenticated user
```

## Support

If you encounter issues:
1. Check backend logs for detailed error messages
2. Check Flutter debug console for client-side errors
3. Verify all environment variables are set correctly
4. Ensure Firebase project configuration matches on both frontend and backend
5. Test backend endpoints directly using Postman or curl

---

**Last Updated:** December 25, 2025
**Status:** ✅ Implemented and Ready for Testing

