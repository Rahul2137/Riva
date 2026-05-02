from google import genai

# Ensure your API Key is valid and active
client = genai.Client(api_key="", http_options={'api_version': 'v1alpha'})

print("Fetching models...")
try:
    for m in client.models.list():
        # The SDK uses 'supported_actions' for the list of capabilities
        if 'bidiGenerateContent' in m.supported_actions:
            print(f"✅ SUPPORTED FOR LIVE: {m.name}")
        else:
            print(f"❌ Standard only: {m.name}")
except Exception as e:
    print(f"An error occurred: {e}")