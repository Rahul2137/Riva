"""
Quick test script to verify backend authentication endpoint is working.
This simulates what the Flutter app does.

Usage:
    python test_login.py <firebase_id_token>

Note: Get a Firebase ID token by:
1. Run the Flutter app with debug logging
2. Copy the ID token from logs after successful Google Sign-In
3. Paste it as the argument to this script
"""

import sys
import requests
import json

def test_login(id_token: str, base_url: str = "http://localhost:8000"):
    """Test the /auth/login endpoint"""
    
    print("🧪 Testing RIVA Authentication Endpoint")
    print(f"📡 Backend URL: {base_url}")
    print(f"🔑 ID Token: {id_token[:50]}...")
    print()
    
    # Test login endpoint
    try:
        response = requests.post(
            f"{base_url}/auth/login",
            json={"idToken": id_token},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        print(f"📊 Status Code: {response.status_code}")
        print(f"📄 Response:")
        print(json.dumps(response.json(), indent=2))
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print("\n✅ Login Test PASSED!")
                print(f"   User: {data['user']['name']} ({data['user']['email']})")
                print(f"   User ID: {data['user']['user_id']}")
                print(f"   New User: {data['user']['is_new_user']}")
                return True
            else:
                print("\n❌ Login Test FAILED: Unsuccessful response")
                return False
        else:
            print(f"\n❌ Login Test FAILED: HTTP {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("\n❌ CONNECTION ERROR: Cannot reach backend")
        print("   Make sure the backend is running on port 8000")
        return False
    except requests.exceptions.Timeout:
        print("\n❌ TIMEOUT ERROR: Backend did not respond in time")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return False


def test_health(base_url: str = "http://localhost:8000"):
    """Test if backend is reachable"""
    print("🏥 Testing Backend Health...")
    try:
        response = requests.get(f"{base_url}/docs", timeout=5)
        if response.status_code == 200:
            print("✅ Backend is reachable")
            return True
        else:
            print(f"⚠️  Backend returned status: {response.status_code}")
            return False
    except:
        print("❌ Backend is NOT reachable")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("RIVA Authentication Test Script")
    print("=" * 60)
    print()
    
    # Parse arguments
    if len(sys.argv) < 2:
        print("❌ Error: Missing Firebase ID token")
        print()
        print("Usage:")
        print("    python test_login.py <firebase_id_token>")
        print()
        print("To get an ID token:")
        print("1. Run the Flutter app and sign in with Google")
        print("2. Check the debug console for the ID token")
        print("3. Copy the token and pass it to this script")
        print()
        print("Quick test without token:")
        test_health()
        sys.exit(1)
    
    id_token = sys.argv[1]
    base_url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"
    
    # First check if backend is reachable
    if not test_health(base_url):
        print()
        print("💡 Tip: Start the backend with:")
        print("   cd riva-ml/app")
        print("   python main.py")
        sys.exit(1)
    
    print()
    
    # Test login
    success = test_login(id_token, base_url)
    
    print()
    print("=" * 60)
    sys.exit(0 if success else 1)

