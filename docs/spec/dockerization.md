# Dockerization Runbook

This document defines one standard workflow:

1. Build and publish a multi-arch image to GHCR.
2. Deploy that versioned image on AMD64 Linux.

## Linux Prerequisites

Install and verify these on the Linux target host before deployment:

1. Docker Engine (recommended 24+)
2. Docker Compose plugin (recommended v2+)
3. Git
4. Network access to required API endpoints used by the app

Verification commands:

```bash
docker --version
docker compose version
git --version
```

If your Linux user is not in the docker group, either use `sudo` for Docker commands or add the user to the docker group and re-login.

## Standard Build And Release (Mac Apple Silicon)

This project now uses uv-native dependency management only:

1. [pyproject.toml](../../pyproject.toml)
2. [uv.lock](../../uv.lock)

Run from repository root:

```bash
git pull
export GHCR_TOKEN="your_ghcr_token"
./docker/release_ghcr.sh
```

Configuration is centralized at the top of [docker/release_ghcr.sh](../../docker/release_ghcr.sh). Update these once:

1. `GHCR_OWNER`
2. `IMAGE_NAME`
3. `PLATFORMS`
4. `PUBLISH_LATEST`

The script automatically:

1. Prepares/uses buildx builder
2. Logs in to GHCR
3. Builds and pushes multi-arch image
4. Verifies manifest
5. Prints IMAGE_REPO and IMAGE_TAG for deployment

If needed, verify manifest manually:

```bash
docker buildx imagetools inspect ghcr.io/<org-or-user>/planbot-proposal-server:vYYYYMMDD-<gitsha>
```

## Standard Deploy And Test (Linux AMD64)

Deployment and API testing instructions are maintained in [docs/spec/README.txt](README.txt).

## Upgrade Procedure

For upgrade/deploy steps, see [docs/spec/README.txt](README.txt).

## Runtime Data And Config Behavior

Current compose setup in [docker-compose.yml](../../docker-compose.yml):

1. Persists outputs:
   - `./log` -> `/app/log`
   - `./runs` -> `/app/runs`
2. Supports optional override folders:
   - `./config-override` -> `/app/config-override` (read-only)
   - `./data-override` -> `/app/data-override` (read-only)
3. If override folders are empty, container uses image defaults copied from:
   - `/app/config-default`
   - `/app/data-default`

This behavior is implemented by [docker/entrypoint.sh](../../docker/entrypoint.sh).
