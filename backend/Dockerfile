FROM python:3.11-slim

WORKDIR /app

# ffmpeg backs OpenCV's HLS/RTSP stream reading (CAMERA_MODE=live pulls each
# camera's video over HTTPS HLS) -- the pip opencv wheel's bundled ffmpeg
# support can be flaky for network streams without the system package.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install the CPU-only torch build explicitly, from PyTorch's own index
# (fully replacing the default index for just this command) -- otherwise pip
# happily resolves the default PyPI torch wheel, which bundles CUDA runtime
# libraries and is several GB larger for no benefit on a GPU-less host.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DATABASE_URL=sqlite:///./data/traffic.db
EXPOSE 8000

# Platforms like Railway inject a dynamic $PORT and route to it; fall back to
# 8000 for plain `docker run`/docker-compose where no PORT is set.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
