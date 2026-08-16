# Planbot Proposal Server Deployment Guide

This guide is intended for GitHub readers who need to:

1. Deploy on Linux.
2. Test proposal APIs from Swagger.

For image build and publish instructions, see [docs/docker/release_runbook.md](docs/docker/release_runbook.md).

Deployment is fully self-contained: the image embeds `compose.yaml` under
`/app/deploy/`, so a `read:packages` GHCR token is the only credential required
— **no source access, no `git` clone**. This document (`README.md`) is
distributed via the GHCR/GitHub page.

## Prerequisites

Install and verify these on the Linux target host:

1. Docker Engine (recommended 24+)
2. Docker Compose plugin (recommended v2+)
3. Network access to the data service and LLM provider endpoints

```bash
docker --version
docker compose version
```

If your Linux user is not in the `docker` group, either use `sudo` for Docker
commands or add the user to the group and re-log in.

## 1. Deploy on Linux (AMD64 or ARM64)

Images are built with an architecture suffix in the tag, so AMD and ARM images
can coexist under the same date+sha. Tag format: `vYYYYMMDD-<gitsha>-<arch>`
(e.g. `v20260816-abc1234-amd64`, `v20260816-abc1234-arm64`).

1. Log in to GHCR and pull the image.
2. Extract `compose.yaml` from the image.
3. Configure `.env` (see section 2).
4. Start the service.

```bash
# 1. log in and pull
echo "$GHCR_TOKEN" | docker login ghcr.io -u <owner> --password-stdin
docker pull ghcr.io/<owner>/planbot-proposal-server:<tag>

# 2. extract compose.yaml from the image
docker run --rm --entrypoint cat \
  ghcr.io/<owner>/planbot-proposal-server:<tag> /app/deploy/compose.yaml > compose.yaml

# 3. configure .env (see section 2)

# 4. start
docker compose up -d
```

Logs and generated proposal artifacts are written to `./log` and `./runs` in
the deployment directory.

**To upgrade to a new version:** re-run section 1 with the new `IMAGE_TAG`
(re-extracting `compose.yaml`, since it may have changed between releases).

## 2. Configure Data Endpoints and Secrets

Point the proposal server at the client's own data service by setting these
environment variables in `.env` (or the compose environment). Create `.env` in
the **same directory as `compose.yaml`** (the project directory) — that is where
`docker compose` reads it from:

| Env var | Overrides | YAML fallback |
|---------|-----------|---------------|
| `DEEPSEEK_API_KEY` | LLM provider key (named by `providers.deepseek.api_key_env`) | *(none — required)* |
| `DATA_CLIENT_BASE_URL` | `data_source.rest.client_base_url` | `http://localhost:8001` |
| `DATA_PRODUCT_BASE_URL` | `data_source.rest.product_base_url` | `http://localhost:8001` |
| `BANK_API_KEY` | REST bearer token (named by `auth_token_env`) | *(none)* |

Example `.env`:

```dotenv
# Compose image resolution (required).
IMAGE_REPO=ghcr.io/<owner>/planbot-proposal-server
IMAGE_TAG=<tag>

# LLM provider key.
DEEPSEEK_API_KEY=<your_key>

# Data endpoints.
DATA_CLIENT_BASE_URL=https://bank-client-data.example.com
DATA_PRODUCT_BASE_URL=https://bank-client-data.example.com
BANK_API_KEY=your_bank_token
```

When an env var is unset, the value in `config/config_planbot.yaml` is used.
`get_client_product_from_restapi` is already `true` in the image default, so the
proposal server reads from the REST data service automatically.

## 3. Verify Deployment Health

```bash
docker compose ps
docker compose logs --tail=200 proposal-server
curl -f http://localhost:8000/docs >/dev/null && echo "docs ok"
curl -f http://localhost:8000/openapi.json >/dev/null && echo "openapi ok"
```

## 4. Test Proposal API in Swagger

1. Open Swagger UI: `http://localhost:8000/docs`
2. Test these endpoints from the UI:

```text
POST /api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings
POST /api/v1/product-opportunity-proposal
POST /api/v1/product-opportunity-proposal-automatch
```

3. For each endpoint:

```text
Click Try it out
Provide request body based on schema examples shown by Swagger
Click Execute
Confirm HTTP 200 and expected JSON response structure
```

## 5. Advanced Configuration

The sections below are optional — the main flow above needs none of them.

### 5.1 Stop the bundled data simulator

By default the container runs **both** the proposal server (port `8000`) and
the bundled data API simulator (port `8001`, serving DuckDB test data). To run
the proposal server only — e.g. when pointing at an external bank data service
— set `START_DATA_SERVER=0`:

```bash
# proposal + data simulator (default)
docker compose up -d

# proposal server only
START_DATA_SERVER=0 docker compose up -d
```

Other launcher variables: `DATA_HOST`/`DATA_PORT` (default `0.0.0.0`/`8001`)
and `PROPOSAL_HOST`/`PROPOSAL_PORT` (default `0.0.0.0`/`8000`).

### 5.2 Override config via files (deep merge)

The container merges any files in `config-override/` (and `data-override/`)
over the image defaults at startup. YAML files are **deep-merged**, so an
override may be *partial*: specify only the keys you want to change and every
unspecified key is inherited from the image default.

A ready-to-copy example lives at
[`config-override/config_planbot.yaml.example`](config-override/config_planbot.yaml.example).
Files ending in `.example` (or `.sample`, `.dist`, `.template`) are ignored by
the container, so the sample is inert as-is. To activate it:

```bash
cp config-override/config_planbot.yaml.example \
   config-override/config_planbot.yaml
```

Example — point the proposal server at the client's own data service:

```yaml
common:
  get_client_product_from_restapi: true
data_source:
  rest:
    client_base_url: https://bank-client-data.example.com
    product_base_url: https://bank-client-data.example.com
    auth_token_env: BANK_API_KEY
```

All other settings (paths, matcher, scorecard weights, etc.) are inherited from
the image's `config/config_planbot.yaml`. Non-YAML files (prompts, `.ini`) are
copied verbatim. Note that merged YAML is re-serialized, so comments in the
default file are not preserved in the merged result.

### 5.3 Map an external folder

The compose file already maps the repo's `./config-override` (and
`./data-override`) into the container read-only:

```yaml
volumes:
  - ./config-override:/app/config-override:ro
  - ./data-override:/app/data-override:ro
```

To use a folder anywhere on the host (e.g. an ops-managed directory), replace
the relative path with an absolute one in `compose.yaml`:

```yaml
volumes:
  - /srv/planbot/config-override:/app/config-override:ro
  - /srv/planbot/data-override:/app/data-override:ro
```

The equivalent with plain `docker run` is:

```bash
docker run -d \
  -v /srv/planbot/config-override:/app/config-override:ro \
  -v /srv/planbot/data-override:/app/data-override:ro \
  -p 8000:8000 \
  ghcr.io/<org-or-user>/planbot-proposal-server:<tag>
```

The container re-reads these folders on every start, so update the YAML and
restart (`docker compose up -d`) to apply changes — no rebuild required.

