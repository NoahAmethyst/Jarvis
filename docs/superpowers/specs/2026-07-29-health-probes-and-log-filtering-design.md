# Health Probes and Access Log Filtering Design

## Goal

Replace production health checks against Swagger `/docs` with dedicated,
low-cost health endpoints and keep those periodic probes out of Uvicorn access
logs without hiding real application traffic.

## HTTP Health Endpoints

Jarvis will expose two schema-hidden endpoints:

- `GET /health/live` returns HTTP 200 with `{"status": "ok"}` whenever the HTTP
  process can serve a request. It performs no database, vector-store, model, or
  external network call.
- `GET /health/ready` returns HTTP 503 with `{"detail": "not ready"}` until
  startup storage and gRPC initialization complete, then HTTP 200 with
  `{"status": "ready"}`.

Both handlers are asynchronous and perform only in-memory reads, so they remain
responsive even when synchronous business requests occupy the AnyIO worker
thread pool.

The readiness flag lives on `app.state`. `serve()` resets it to false before
startup work and sets it true only after storage initialization and gRPC server
startup, immediately before creating the HTTP server.

## Access Log Filtering

The root logging handler will attach a focused filter for `uvicorn.access`
records. It will suppress records whose request path is exactly
`/health/live` or `/health/ready`. All other Uvicorn access records, including
`/docs`, `/chat`, error responses, and other application routes, remain visible.

Disabling Uvicorn access logging globally is intentionally rejected because it
would remove useful request evidence. Merely increasing probe intervals is also
rejected because it leaves Swagger coupled to operational health.

## Deployment Configuration

Kubernetes probes will use:

- readiness: `/health/ready`, retaining the existing 10-second period;
- liveness: `/health/live`, retaining the existing 30-second period.

The Docker image `HEALTHCHECK` will use `/health/live`. Health endpoints will
remain inexpensive and will not validate LLM, PostgreSQL, or Qdrant on every
probe.

## Testing

Implementation will follow red-green-refactor:

- endpoint tests for live 200, ready 503, and ready 200;
- a startup test proving readiness is set only after initialization;
- logging filter tests proving health paths are dropped and real paths remain;
- manifest assertions for the dedicated probe paths;
- focused tests, the full test suite, Python compilation, and staged diff
  validation before publication.

## Deployment

After the code is pushed and GitHub Actions succeeds, synchronize only the
sanitized `jarvis.yaml` to `/root/jarvis/jarvis.yaml`, apply that manifest, and
verify the Deployment rollout, probe paths, health responses, and absence of
periodic health access-log noise. No local secret-bearing manifest will be
committed.
