FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    SMARTSORT_APP_DATA=/data/sessions SMARTSORT_ALLOW_LOCAL_TRAIN=false \
    OMP_NUM_THREADS=2 SMARTSORT_CPU_THREADS=2
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-server.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install 'torch>=2.6,<3' 'torchvision>=0.21,<1' --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install -r requirements-server.txt
COPY smartsort_app ./smartsort_app
COPY serve.py ./
RUN mkdir -p /data/sessions
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/healthz',timeout=4)"
CMD ["python", "serve.py"]
