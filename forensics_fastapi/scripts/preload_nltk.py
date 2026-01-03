import os
import sys

import nltk

# Default to /root/nltk_data if NLTK_DATA_PATH not set
NLTK_DATA_PATH = os.environ.get("NLTK_DATA_PATH", "/root/nltk_data")

# 1. CRITICAL: Tell NLTK about this path immediately
if NLTK_DATA_PATH not in nltk.data.path:
    nltk.data.path.append(NLTK_DATA_PATH)

def preload_nltk():
    sentinel_file = os.path.join(NLTK_DATA_PATH, "nltk_setup_complete.flag")

    # 2. Check if we have already set this up in the mounted bucket
    if os.path.exists(sentinel_file):
        print(f"NLTK data found at {NLTK_DATA_PATH}. Skipping download.")
        verify_install() # Optional: Run verification to be safe
        return

    print(f"Preloading NLTK data to {NLTK_DATA_PATH}...")
    
    if not os.path.exists(NLTK_DATA_PATH):
        print(f"Creating directory {NLTK_DATA_PATH}")
        os.makedirs(NLTK_DATA_PATH, exist_ok=True)

    packages = [
        'punkt',
        'averaged_perceptron_tagger',
        'stopwords',
        'wordnet',
        'omw-1.4',
        'vader_lexicon'
    ]
    
    try:
        packages.append('punkt_tab')
    except Exception:
        pass

    for pkg in packages:
        try:
            # 3. Check specific package existence to avoid partial corruption
            # (Optional, but good for robustness if previous run crashed)
            try:
                # We try to find it first. Note: This requires mapping pkg names to 
                # types (corpora/tokenizers), so the unconditional download below 
                # with the sentinel file check is usually safer and simpler.
                print(f"Downloading {pkg}...")
                nltk.download(pkg, download_dir=NLTK_DATA_PATH, quiet=True) 
            except Exception as e:
                print(f"Error downloading {pkg}: {e}")
        except Exception as e:
            print(f"Loop Error: {e}")

    # 4. Write the sentinel file to the bucket
    try:
        with open(sentinel_file, 'w') as f:
            f.write("done")
        print("NLTK data preload complete and locked.")
    except Exception as e:
        print(f"Warning: Could not write sentinel file: {e}")
    
    verify_install()

def verify_install():
    try:
        from nltk.tokenize import word_tokenize
        # Ensure 'punkt' is actually loadable
        word_tokenize("NLTK is preloaded successfully.")
        print("Verification: Tokenizing test sentence passed.")
    except LookupError:
        print("Verification failed: Packages missing. Removing sentinel to retry next boot.")
        # If verification fails, delete sentinel so it retries next time
        sentinel_file = os.path.join(NLTK_DATA_PATH, "nltk_setup_complete.flag")
        if os.path.exists(sentinel_file):
            os.remove(sentinel_file)
        sys.exit(1)
    except Exception as e:
        print(f"Verification failed with unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    preload_nltk()
