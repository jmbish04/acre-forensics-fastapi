#!/bin/bash
set -e

# Default Evidence Path structure
EVIDENCE_DIR="/workspace/src/forensics/evidence"
MOUNT_POINT="/mnt/evidence"

# --- Defaults --- #
export PYTHONUNBUFFERED=${PYTHONUNBUFFERED:-1}
export PORT=${PORT:-8000}

# Default Bucket Names if not set in Env
export R2_EVIDENCE_BUCKET_NAME=${R2_EVIDENCE_BUCKET_NAME:-"acre-forensics-evidence"}
export R2_DOC_PAGES_BUCKET_NAME=${R2_DOC_PAGES_BUCKET_NAME:-"acre-forensics-doc-pages"}
export R2_DOC_AI_SEARCH_BUCKET_NAME=${R2_DOC_AI_SEARCH_BUCKET_NAME:-"acre-forensics-doc-ai-search"}
export R2_REPORTS_BUCKET_NAME=${R2_REPORTS_BUCKET_NAME:-"acre-forensics-reports"}
export R2_SYS_MISC_BUCKET_NAME=${R2_SYS_MISC_BUCKET_NAME:-"acre-forensics-sys-misc"}

echo "=== Container Boot: Starting Application ==="
echo "PORT: $PORT"
echo "PYTHONUNBUFFERED: $PYTHONUNBUFFERED"

# Create Local Evidence Directory
mkdir -p "$EVIDENCE_DIR"
echo "Created local evidence directory: $EVIDENCE_DIR"

# Resolve R2 Endpoint
if [ -n "$R2_ENDPOINT_URL" ]; then
    R2_ENDPOINT="${R2_ENDPOINT_URL%/}"  # Strip trailing slash
elif [ -n "$R2_ACCOUNT_ID" ]; then
    R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
else
    echo "⚠️  Missing R2_ENDPOINT_URL or R2_ACCOUNT_ID. Cannot mount R2 buckets."
fi

# R2 Compatibility Settings
export AWS_REGION="auto"

# Debug Logs for Credentials (Masked)
if [ -n "$AWS_ACCESS_KEY_ID" ]; then
    echo "AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:0:5}*****"
else
    echo "AWS_ACCESS_KEY_ID: (MISSING)"
fi

if [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "AWS_SECRET_ACCESS_KEY: (SET)"
else
    echo "AWS_SECRET_ACCESS_KEY: (MISSING)"
fi

echo "R2_ENDPOINT: $R2_ENDPOINT"

# Function to mount a bucket
mount_bucket() {
    local bucket_name=$1
    local mount_path=$2
    
    if [ -n "$bucket_name" ] && [ -n "$R2_ENDPOINT" ] && [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
        echo "Mounting $bucket_name -> $mount_path"
        mkdir -p "$mount_path"
        /usr/local/bin/tigrisfs --endpoint "${R2_ENDPOINT}" -f "${bucket_name}" "$mount_path" &
    else
        echo "Skipping mount for $bucket_name (missing creds or name via env)"
    fi
}

echo "=== Mounting R2 Buckets ==="

# 1. Evidence
mount_bucket "$R2_EVIDENCE_BUCKET_NAME" "/r2/evidence"
# Sync/Link Application Evidence Path
# If the app expects it at /workspace/src/forensics/evidence, we rely on App config or symlink
# Removing local dir if exists to safely symlink? No, dangerous.
# We'll validatethe app reads from /r2/evidence separately or via config, 
# for now we just adhere to the requested structure.

# 2. Doc Pages
mount_bucket "$R2_DOC_PAGES_BUCKET_NAME" "/r2/doc_pages"

# 3. Doc AI Search
mount_bucket "$R2_DOC_AI_SEARCH_BUCKET_NAME" "/r2/doc_ai_search"

# 4. Reports
mount_bucket "$R2_REPORTS_BUCKET_NAME" "/r2/reports"

# 5. Sys Misc (NLTK)
# Request: R2_SYS_MISC_PATH="/root" -> We mount to /r2/sys_misc then symlink specific folders
mount_bucket "$R2_SYS_MISC_BUCKET_NAME" "/r2/sys_misc"

echo "Waiting for mounts to settle..."
sleep 3

# Setup System Symlinks (NLTK)
# Force persistence if bucket mounted
if [ -d "/r2/sys_misc" ]; then
    echo "Configuring NLTK persistence..."
    
    # 1. Create remote dir if missing
    mkdir -p /r2/sys_misc/nltk_data
    
    # 2. Link /root/nltk_data -> /r2/sys_misc/nltk_data
    # Remove existing local folder/link if exists
    rm -rf /root/nltk_data
    # Link
    ln -sfn /r2/sys_misc/nltk_data /root/nltk_data
    echo "Linked /root/nltk_data -> /r2/sys_misc/nltk_data"
    
    # 3. Download/Verify NLTK Data
    echo "Downloading NLTK data to ensure cache..."
    # We download key packages. If already present, nltk skips handling.
    python3 -m nltk.downloader -d /root/nltk_data punkt punkt_tab stopwords averaged_perceptron_tagger wordnet || echo "NLTK Download Warning"
fi

# Link Evidence Dir if requested by App structure
# App uses EVIDENCE_DIR="/workspace/src/forensics/evidence"
if [ -d "/r2/evidence" ]; then
    echo "Linking Evidence Directory..."
    # Ensure parent exists
    mkdir -p /workspace/src/forensics
    # Remove empty placeholder
    if [ -z "$(ls -A /workspace/src/forensics/evidence 2>/dev/null)" ]; then
        rm -rf /workspace/src/forensics/evidence
        ln -s /r2/evidence /workspace/src/forensics/evidence
        echo "Linked /workspace/src/forensics/evidence -> /r2/evidence"
    fi
fi

echo "=== Mounnting Complete. R2 Structure: ==="
ls -R /r2 || echo "/r2 not created"


echo "=== Boot Complete. Starting Application ==="
exec "$@"
