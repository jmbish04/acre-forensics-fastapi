# Stage 1: Builder
FROM docker.io/cloudflare/sandbox:0.3.3 AS builder

WORKDIR /workspace

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    build-essential \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# [FIX] Copy only pyproject.toml initially. uv.lock is generated in the next step.
COPY pyproject.toml .

# [FIX] Run 'uv lock' to generate the lockfile, then export.
# We remove '--frozen' because we are generating the lockfile on the fly.
RUN pip install uv && \
    uv lock && \
    uv export --no-hashes --format requirements-txt --output-file requirements.txt && \
    pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM docker.io/cloudflare/sandbox:0.3.3

WORKDIR /workspace

# Install runtime dependencies and Node.js/Wrangler
RUN apt-get update && apt-get install -y \
    libmagic1 \
    libpq-dev \
    curl \
    gnupg \
    git \
    procps \
    vim \
    nano \
    tesseract-ocr \
    ocrmypdf \
    poppler-utils \
    ghostscript \
    qpdf \
    unpaper \
    s3fs \
    fuse \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g wrangler \
    && rm -rf /var/lib/apt/lists/*

# Install uv AND uvicorn[standard] to enable WebSockets
RUN pip install uv "uvicorn[standard]"

# Copy installed python packages from builder
# ### DO NOT CHANGE THE COPY PATH BELOW ###
COPY --from=builder /install/local /usr/local

# Copy application code
COPY forensics_fastapi/ /workspace/forensics_fastapi/

# Copy Boot Script
COPY src/sandboxsdk/boot.sh /boot.sh
RUN chmod +x /boot.sh

# Setup directories
RUN mkdir -p /workspace/src && \
    ln -s /workspace/forensics_fastapi/forensics /workspace/src/forensics && \
    mkdir -p /workspace/src/forensics/evidence && \
    mkdir -p /workspace/src/reports/output_final && \
    mkdir -p /workspace/src/data && \
    mkdir -p /workspace/logs

EXPOSE 8000
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/boot.sh"]
CMD ["python3", "-m", "uvicorn", "forensics_fastapi.forensics.api:app", "--host", "0.0.0.0", "--port", "8000"]
