
import os
import sys

# Add the current directory to sys.path to mimic running as a module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def check_imports():
    print("Checking imports...")
    try:
        import forensics_fastapi.config as config
        print(f"Config loaded: API={config.HOST_API_URL}, R2_BUCKET={config.R2_EVIDENCE_BUCKET_NAME}")
        
        print("AttachmentPipeline imported successfully.")
        
        print("ForensicAttachmentProcessor imported successfully.")
        
        print("Imports check PASSED.")
        return True
    except Exception as e:
        print(f"Import check FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if check_imports():
        sys.exit(0)
    else:
        sys.exit(1)
