# API-only mode: ComfyUI and ai-toolkit are host-native and out of scope for this container.
FROM python:3.12-slim
WORKDIR /app
# OpenCV is required by face scoring and person masks. The slim base omits the
# libGL.so.1 runtime library that cv2 loads even for headless ML operations.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt backend/requirements.txt
COPY backend/requirements-ml.txt backend/requirements-ml.txt
COPY backend/requirements-scrape.txt backend/requirements-scrape.txt
COPY backend/requirements-docker-extras.txt backend/requirements-docker-extras.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
# These tools run in-process, so installing them only after the container starts
# makes a successful setup vanish on the next image rebuild.  The Docker-only
# bundle is the safe subset: LaMa stays in its dedicated venv because it needs a
# Pillow version incompatible with the API's Pillow pin.
RUN pip install --no-cache-dir -r backend/requirements-docker-extras.txt \
    -c backend/requirements-ml.txt
COPY backend backend
COPY frontend/dist frontend/dist
COPY config.example.json .
COPY packaging/docker/seed_comfy_config.py /app/packaging/docker/seed_comfy_config.py
COPY packaging/docker/studio_api_entrypoint.sh /usr/local/bin/studio-api-entrypoint.sh
RUN chmod 755 /usr/local/bin/studio-api-entrypoint.sh
ENV LDS_DATA_DIR=/data \
    LDS_CONFIG=/data/config.json \
    LDS_HOST=0.0.0.0 \
    LDS_PORT=5051 \
    LDS_AUTO_PORT=0 \
    LDS_DOCKER_COMFY_MODE=none
EXPOSE 5051
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5051/api/health', timeout=3).read()"]
ENTRYPOINT ["/usr/local/bin/studio-api-entrypoint.sh"]
