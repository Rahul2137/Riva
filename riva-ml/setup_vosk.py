"""
Vosk Model Setup Script
Downloads and extracts the Vosk speech recognition model.
"""
import os
import sys
import urllib.request
import zipfile
from pathlib import Path


# Model configurations
MODELS = {
    "small": {
        "name": "vosk-model-small-en-us-0.15",
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        "size": "40 MB",
        "description": "Small model - Fast, good for production"
    },
    "medium": {
        "name": "vosk-model-en-us-0.22",
        "url": "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip",
        "size": "1.8 GB",
        "description": "Medium model - Better accuracy, slower"
    }
}


def download_model(model_type: str = "small"):
    """
    Download and extract Vosk model.
    
    Args:
        model_type: "small" or "medium"
    """
    if model_type not in MODELS:
        print(f"Error: Invalid model type '{model_type}'. Choose 'small' or 'medium'.")
        return False
    
    model_info = MODELS[model_type]
    model_name = model_info["name"]
    model_url = model_info["url"]
    
    # Create models directory
    base_dir = Path(__file__).parent / "app" / "models"
    base_dir.mkdir(exist_ok=True, parents=True)
    
    model_dir = base_dir / model_name
    zip_path = base_dir / f"{model_name}.zip"
    
    # Check if model already exists
    if model_dir.exists():
        print(f"[OK] Model already exists at: {model_dir}")
        return True
    
    print(f"\n{'='*60}")
    print(f"Downloading Vosk Model: {model_name}")
    print(f"Size: {model_info['size']}")
    print(f"Description: {model_info['description']}")
    print(f"{'='*60}\n")
    
    try:
        # Download model
        print(f"Downloading from: {model_url}")
        print("This may take a few minutes depending on your connection...")
        
        def progress_hook(block_num, block_size, total_size):
            downloaded = block_num * block_size
            percent = min(downloaded * 100 / total_size, 100)
            sys.stdout.write(f"\rProgress: {percent:.1f}%")
            sys.stdout.flush()
        
        urllib.request.urlretrieve(model_url, zip_path, progress_hook)
        print("\n[OK] Download complete!")
        
        # Extract model
        print(f"Extracting to: {base_dir}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(base_dir)
        
        print("[OK] Extraction complete!")
        
        # Clean up zip file
        zip_path.unlink()
        print("[OK] Cleaned up temporary files")
        
        print(f"\n{'='*60}")
        print(f"[SUCCESS] Vosk model installed successfully!")
        print(f"Location: {model_dir}")
        print(f"{'='*60}\n")
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Failed to download/extract model: {e}")
        # Clean up on failure
        if zip_path.exists():
            zip_path.unlink()
        return False


def main():
    """Main setup function."""
    print("\n" + "="*60)
    print("Vosk Model Setup for RIVA")
    print("="*60 + "\n")
    
    print("Available models:")
    for key, info in MODELS.items():
        print(f"  [{key}] {info['name']}")
        print(f"      Size: {info['size']}")
        print(f"      {info['description']}")
        print()
    
    # Get user choice
    if len(sys.argv) > 1:
        model_type = sys.argv[1].lower()
    else:
        choice = input("Which model would you like to download? (small/medium) [small]: ").strip().lower()
        model_type = choice if choice in MODELS else "small"
    
    success = download_model(model_type)
    
    if success:
        print("\nNext steps:")
        print("1. Install Vosk: pip install vosk")
        print("2. Start your backend: python app/main.py")
        print("\nVosk is now ready to use!")
    else:
        print("\nSetup failed. Please try again or download manually from:")
        print("https://alphacephei.com/vosk/models")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

