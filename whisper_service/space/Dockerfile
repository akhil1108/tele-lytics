FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/data/hf-cache

# ffmpeg decodes the m4a/mp3/ogg/opus/amr formats the backend may send.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
# This Space runs on a T4 GPU — install the CUDA build of the matched
# torch/torchaudio pair first (see requirements.txt's own comment on why
# they're pinned as a set), then the rest. requirements.txt also pins
# torch==2.4.1/torchaudio==2.4.1; pip sees the CUDA build already satisfies
# that exact version and leaves it alone rather than reinstalling the CPU
# wheel from PyPI's default index.
RUN pip install --upgrade pip \
    && pip install torch==2.4.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu121 \
    && pip install -r requirements.txt

COPY config.py models.py main.py ./

# Hugging Face Spaces runs Docker containers as UID 1000 regardless of the
# Dockerfile's own USER directive — matching it here (rather than the
# arbitrary 10001 the top-level Dockerfile uses for non-Spaces deployment)
# avoids permission errors on /app and /data at runtime.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data/hf-cache \
    && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
