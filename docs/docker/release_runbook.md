# Dockerization Runbook — Build & Publish

This document describes how to build and publish the Docker image to GHCR.
Deployment and API testing instructions live in [README.md](../../README.md).

## Build & Publish

This project uses uv-native dependency management:

1. [pyproject.toml](../../pyproject.toml)
2. [uv.lock](../../uv.lock)

Run from repository root:

```bash
git pull
export GHCR_TOKEN="your_ghcr_token"
./docker/release_ghcr.sh                 # amd64, local (build only)
./docker/release_ghcr.sh arm64           # arm64, local (build only)
./docker/release_ghcr.sh amd64 publish   # amd64, build and push to GHCR
./docker/release_ghcr.sh arm64 publish   # arm64, build and push to GHCR
```

Configuration is centralized at the top of [docker/release_ghcr.sh](../../docker/release_ghcr.sh). Update these once:

1. `GHCR_OWNER`
2. `IMAGE_NAME`
3. `PUBLISH_LATEST`

Two positional switches control build behaviour (in order):

1. **Architecture** (default `amd64`): `amd64` → `linux/amd64`, `arm64` → `linux/arm64`.
2. **Publish mode** (default `local`): `local` → build and load into the local
   Docker daemon (no push, no GHCR token); `publish` → build and push to GHCR.

The tag includes the architecture so AMD and ARM images coexist under the same
date+sha: `vYYYYMMDD-<gitsha>-<arch>` (e.g. `v20260816-abc1234-amd64`).

The script automatically:

1. Resolves the repo root (so it works from any working directory).
2. Prepares/uses a buildx builder (cross-compiles to the target platform).
3. Logs in to GHCR (publish mode only).
4. Builds and pushes (or loads) the image for the target platform.
5. Verifies the pushed image (publish mode only).
6. Prints `IMAGE_REPO`, `IMAGE_TAG`, and `PUBLISH_MODE` for deployment.

If needed, verify the pushed image manually:

```bash
docker buildx imagetools inspect ghcr.io/<org-or-user>/planbot-proposal-server:vYYYYMMDD-<gitsha>-<arch>
```

> Note: `--load` only works for the host's native architecture. On Apple Silicon
> use `arm64 local` for local testing; `amd64` must be published (`amd64 publish`).

## Test a locally built image

After `./docker/release_ghcr.sh arm64 local` (build only, loaded into the local
daemon), find the built tag:

```bash
docker images --format '{{.Repository}}:{{.Tag}}' | grep planbot
```

Then run it directly with the same mounts/ports as `compose.yaml`. Run from the
repository root so `$(pwd)/log` and `$(pwd)/runs` resolve to the repo folders:

```bash
docker run -d \
  --name planbot_proposal_server \
  --restart unless-stopped \
  -p 8000:8000 \
  -p 8001:8001 \
  -e DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}" \
  -e SERPAPI_API_KEY="${SERPAPI_API_KEY:-}" \
  -e START_DATA_SERVER=true \
  -e HF_HOME=/app/hf-cache \
  -v "$(pwd)/log:/app/log" \
  -v "$(pwd)/runs:/app/runs" \
  -v hf-cache:/app/hf-cache \
  ghcr.io/roger249/planbot-proposal-server:v20260904-8fb8a01-arm64
```

Substitute the actual tag printed by the build script (or from `docker images`).

Verify the server is up:

```bash
curl -f http://localhost:8000/docs
docker exec planbot_proposal_server ls -la /app/runs
```

Generated proposals appear in the repo's `runs/` folder (bind-mounted). Stop and
clean up when done:

```bash
docker rm -f planbot_proposal_server
```

> If ports 8000/8001 are already in use (e.g. a previously started container),
> stop that container first with `docker rm -f <name>`. Note that a plain
> `docker run` only gets the bind mounts you pass with `-v`; a container started
> without them keeps `runs`/`log` inside its own writable layer.

## Deployment Bundle

The image embeds `compose.yaml` under `/app/deploy/`, so clients can deploy
without source access. Extraction and deployment steps are in
[README.md](../../README.md).
