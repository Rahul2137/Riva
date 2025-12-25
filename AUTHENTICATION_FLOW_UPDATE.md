# RIVA Authentication Flow - Updated Implementation

## 🎯 What Changed

The authentication flow has been updated so that:
1. ✅ Backend returns **JSON response** (not redirect)
2. ✅ Proper **HTTP status codes**: 201 for new users, 200 for existing users
3. ✅ Response includes **token** and complete **user info**
4. ✅ Frontend **automatically navigates** to home page after successful login
5. ✅ No manual navigation needed - handled by auth state listener

---

## 📊 Updated Authentication Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. USER clicks "Sign in with Google" in Flutter App            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Google Sign-In Dialog → Firebase Authentication             │
│    - User selects Google account                               │
│    - Firebase creates session                                  │
│    - Returns Firebase ID Token                                 │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ POST /auth/login
                         │ {"idToken": "eyJhbG..."}
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. BACKEND: Verify & Process                                   │
│    - Verify Firebase token                                     │
│    - Extract user info (uid, email, name, picture)             │
│    - Check if user exists in MongoDB                           │
│    - Create new user OR update existing user                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ HTTP 201 (new user) or 200 (existing)
                         │ {
                         │   "success": true,
                         │   "message": "Login successful",
                         │   "token": "eyJhbG...",
                         │   "user": {...},
                         │   "is_new_user": false
                         │ }
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. FRONTEND: Store & Navigate                                  │
│    - Store token in local storage                              │
│    - AuthProvider updates auth state to "authenticated"        │
│    - AuthGate automatically detects state change               │
│    - App navigates to MainLayout (home page)                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔧 Backend Changes

### File: `riva-ml/app/main.py`

#### 1. Updated Response Model
```python
class LoginResponse(BaseModel):
    success: bool
    message: str
    token: str              # NEW: Return token for frontend
    user: dict             # User data from database
    is_new_user: bool      # NEW: Flag to indicate if user is new
```

#### 2. Updated Login Endpoint
```python
@app.post("/auth/login", status_code=200)
async def firebase_login(request: LoginRequest, response: Response):
    # ... verification logic ...
    
    # Set status code: 201 for new user, 200 for existing
    response.status_code = 201 if is_new_user else 200
    
    return LoginResponse(
        success=True,
        message="New user created" if is_new_user else "Login successful",
        token=request.idToken,  # Return Firebase token
        user=user_data,
        is_new_user=is_new_user
    )
```

**Response Examples:**

**New User (201):**
```json
{
  "success": true,
  "message": "New user created",
  "token": "eyJhbGciOiJSUzI1NiIs...",
  "user": {
    "user_id": "abc123xyz",
    "email": "user@example.com",
    "name": "John Doe",
    "picture": "https://lh3.googleusercontent.com/...",
    "created_at": "2025-12-25T10:30:00.000Z",
    "last_login": "2025-12-25T10:30:00.000Z",
    "timezone": "UTC"
  },
  "is_new_user": true
}
```

**Existing User (200):**
```json
{
  "success": true,
  "message": "Login successful",
  "token": "eyJhbGciOiJSUzI1NiIs...",
  "user": {
    "user_id": "abc123xyz",
    "email": "user@example.com",
    "name": "John Doe",
    "picture": "https://lh3.googleusercontent.com/...",
    "created_at": "2025-12-20T08:15:00.000Z",
    "last_login": "2025-12-25T10:30:00.000Z",
    "timezone": "UTC"
  },
  "is_new_user": false
}
```

---

## 📱 Frontend Changes

### File: `riva_frontend/lib/services/api_service.dart`

#### Updated to Handle Both Status Codes
```dart
// Accept both 200 (existing user) and 201 (new user)
if (response.statusCode == 200 || response.statusCode == 201) {
  final data = json.decode(response.body);
  if (data['success'] == true) {
    // Log user info
    final isNewUser = data['is_new_user'] ?? false;
    final userName = data['user']['name'] ?? 'Unknown';
    log('[OK] ${isNewUser ? 'New user created' : 'Login successful'}: $userName');
    return data;
  }
}
```

### File: `riva_frontend/lib/providers/auth_provider.dart`

#### Enhanced Response Handling
```dart
// Send token to backend for verification and user creation
final response = await ApiService.loginUser(idToken);
if (response == null) {
  log('[WARNING] Backend login failed, but Firebase auth succeeded');
  // Still allow login even if backend fails (offline mode)
} else {
  final isNewUser = response['is_new_user'] ?? false;
  final userName = response['user']['name'] ?? 'User';
  log('[OK] Backend login successful: $userName (${isNewUser ? 'New User' : 'Existing User'})');
  
  // Store backend token if different from Firebase token
  if (response['token'] != null) {
    await StorageService.saveAuthToken(response['token']);
  }
}

// Navigation will be handled automatically by auth state listener
```

### File: `riva_frontend/lib/main.dart`

#### Automatic Navigation via AuthGate
```dart
class AuthGate extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Consumer<app_auth.AuthProvider>(
      builder: (context, authProvider, _) {
        // Show loading while checking auth state
        if (authProvider.status == app_auth.AuthStatus.unknown) {
          return LoadingScreen();
        }

        // Automatically navigate to MainLayout when authenticated
        if (authProvider.isAuthenticated) {
          return const MainLayout();  // HOME PAGE
        }

        // Show login screen if not authenticated
        return const LoginScreen();
      },
    );
  }
}
```

**How Navigation Works:**
1. User logs in successfully
2. Firebase auth state changes to authenticated
3. `AuthProvider` detects state change via listener
4. `AuthProvider.status` updates to `AuthStatus.authenticated`
5. `AuthGate` widget rebuilds (via `Consumer`)
6. `AuthGate` sees `isAuthenticated == true`
7. **Automatically shows `MainLayout` (home page)**

---

## ✅ Benefits of This Implementation

### 1. **Proper HTTP Status Codes**
- `200 OK` - Existing user logged in successfully
- `201 Created` - New user account created
- `401 Unauthorized` - Invalid token
- `500 Internal Server Error` - Server-side error

### 2. **Complete User Information**
Frontend receives:
- User ID (from Firebase)
- Email
- Name
- Profile picture URL
- Account creation date
- Last login timestamp
- New user flag

### 3. **Automatic Navigation**
- No manual navigation code needed
- Handled by auth state listener
- Clean separation of concerns
- Works consistently across app

### 4. **Offline Support**
- Firebase auth works even if backend fails
- User can still access app
- Backend syncs when available

### 5. **Token Management**
- Token stored in secure local storage
- Available for future API calls
- Automatic refresh via Firebase

---

## 🧪 Testing the Flow

### Step 1: Start Backend
```bash
cd riva-ml/app
..\venv\Scripts\Activate.ps1
python main.py
```

Look for:
```
[OK] Firebase Admin SDK initialized
INFO: Uvicorn running on http://0.0.0.0:8000
```

### Step 2: Run Flutter App
```bash
cd riva_frontend
flutter run
```

### Step 3: Test Login

**Expected Console Output (Backend):**
```
[OK] New user created: user@example.com
INFO: 127.0.0.1:12345 - "POST /auth/login HTTP/1.1" 201 Created
```
OR
```
[OK] User updated: user@example.com
INFO: 127.0.0.1:12345 - "POST /auth/login HTTP/1.1" 200 OK
```

**Expected Console Output (Flutter):**
```
Login response status: 201
[OK] New user created: John Doe
[OK] Backend login successful: John Doe (New User)
User authenticated: user@example.com
```

**Expected Behavior:**
1. ✅ Login screen shows
2. ✅ User clicks "Sign in with Google"
3. ✅ Google account selection dialog appears
4. ✅ User selects account
5. ✅ Backend receives request and responds
6. ✅ **App automatically navigates to home screen**
7. ✅ User sees MainLayout (home page)

---

## 📋 API Reference

### POST /auth/login

**Request:**
```http
POST /auth/login HTTP/1.1
Content-Type: application/json

{
  "idToken": "eyJhbGciOiJSUzI1NiIsImtpZCI6..."
}
```

**Success Response (New User):**
```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "success": true,
  "message": "New user created",
  "token": "eyJhbGciOiJSUzI1NiIsImtpZCI6...",
  "user": {
    "user_id": "firebase_uid",
    "email": "user@example.com",
    "name": "John Doe",
    "picture": "https://...",
    "created_at": "2025-12-25T10:30:00.000Z",
    "last_login": "2025-12-25T10:30:00.000Z",
    "timezone": "UTC"
  },
  "is_new_user": true
}
```

**Success Response (Existing User):**
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "success": true,
  "message": "Login successful",
  "token": "eyJhbGciOiJSUzI1NiIsImtpZCI6...",
  "user": { ... },
  "is_new_user": false
}
```

**Error Response:**
```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "detail": "Invalid authentication token"
}
```

---

## 🔐 Security Notes

1. **Token Verification**: Every login request verifies the Firebase token
2. **User Creation**: New users are automatically created in MongoDB
3. **Token Storage**: Tokens stored securely in Flutter's secure storage
4. **HTTPS**: Use HTTPS in production for all API calls
5. **Token Expiry**: Firebase tokens expire after 1 hour (auto-refreshed)

---

## 🎯 Summary

### What Works Now:
- ✅ Backend returns JSON (no redirect)
- ✅ Proper status codes (200/201)
- ✅ Complete user info in response
- ✅ Token included for future API calls
- ✅ Frontend stores token automatically
- ✅ **Automatic navigation to home page**
- ✅ Clean, maintainable code
- ✅ Offline support (Firebase-first)

### No Manual Navigation Needed:
The `AuthGate` widget automatically handles navigation by listening to auth state changes. When the user logs in successfully, the auth state changes and the app automatically shows the home page.

---

**Status:** ✅ **READY FOR TESTING**

**Last Updated:** December 25, 2025

**Backend Running:** Terminal 11, Process 19376, Port 8000

