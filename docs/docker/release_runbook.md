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
./docker/release_ghcr.sh                 # amd64, publish (default)
./docker/release_ghcr.sh arm64           # arm64, publish
./docker/release_ghcr.sh amd64 local     # amd64, build only (no push)
./docker/release_ghcr.sh arm64 local     # arm64, build only for local testing
```

Configuration is centralized at the top of [docker/release_ghcr.sh](../../docker/release_ghcr.sh). Update these once:

1. `GHCR_OWNER`
2. `IMAGE_NAME`
3. `PUBLISH_LATEST`

Two positional switches control build behaviour (in order):

1. **Architecture** (default `amd64`): `amd64` → `linux/amd64`, `arm64` → `linux/arm64`.
2. **Publish mode** (default `publish`): `publish` → build and push to GHCR;
   `local` → build and load into the local Docker daemon (no push, no GHCR token).

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

## Deployment Bundle

The image embeds `compose.yaml` under `/app/deploy/`, so clients can deploy
without source access. Extraction and deployment steps are in
[README.md](../../README.md).
