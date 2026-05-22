FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cache dependency layer separately from source
COPY pyproject.toml .
COPY jarvis/__init__.py jarvis/
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

# Regenerate proto stubs and fix package-relative import
RUN python -m grpc_tools.protoc \
    -I jarvis/api/grpc \
    --python_out=jarvis/api/grpc \
    --grpc_python_out=jarvis/api/grpc \
    jarvis/api/grpc/jarvis.proto \
    && sed -i \
    's/^import jarvis_pb2 as jarvis__pb2/from jarvis.api.grpc import jarvis_pb2 as jarvis__pb2/' \
    jarvis/api/grpc/jarvis_pb2_grpc.py


FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

RUN useradd -m -u 1000 jarvis && chown -R jarvis:jarvis /app
USER jarvis

EXPOSE 8080 9090

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/docs')" \
    || exit 1

CMD ["python", "jarvis/main.py"]
