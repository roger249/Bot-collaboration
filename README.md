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
| `BACHERLIER_API_KEY` | LLM provider key (named by `providers.bacherlier.api_key_env`) | *(none — required)* |
| `SERPAPI_API_KEY` | Web search key for the SerpApi tool | *(none — required only for `/api/v1/llm-product-matcher` web search)* |
| `DATA_CLIENT_BASE_URL` | `data_source.rest.client_base_url` | `http://localhost:8001` |
| `DATA_PRODUCT_BASE_URL` | `data_source.rest.product_base_url` | `http://localhost:8001` |
| `BANK_API_KEY` | REST bearer token (named by `auth_token_env`) | *(none)* |

Example `.env`:

```dotenv
# Compose image resolution (required).
IMAGE_REPO=ghcr.io/<owner>/planbot-proposal-server
IMAGE_TAG=<tag>

# LLM provider key.
BACHERLIER_API_KEY=<your_key>

# Web search key (SerpApi) — required only for the LLM product matcher endpoint.
SERPAPI_API_KEY=<your_key>

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
POST /api/v1/llm-product-matcher
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
unspecified key is inherited from the image default. Dicts are merged
recursively; lists are replaced in full.

A ready-to-copy example lives at
[`config-override/config_planbot.yaml.example`](config-override/config_planbot.yaml.example).
Files ending in `.example` (or `.sample`, `.dist`, `.template`) are ignored by
the container, so the sample is inert as-is.

**Step-by-step — switch the LLM model a pipeline uses.** Each proposal
endpoint is backed by a `pipeline.<id>` section whose `execution.model` key
selects the model from `llm_models`. Change it without rebuilding the image:

1. Activate the override file (only the first time):

   ```bash
   cp config-override/config_planbot.yaml.example \
      config-override/config_planbot.yaml
   ```

2. Add a partial override that defines a model under `llm_models` (if the one
   you want isn't already there) and points `execution.model` at it. Here we
   add a `bacherlier`-backed deepseek model and switch two pipelines to it:

   ```yaml
   llm_models:
     bacherlier_deepseek:
       provider: bacherlier
       model: deepseek-v4-flash-0731
       temperature: 0.1

   pipeline:
     product_opportunity:
       execution:
         model: bacherlier_deepseek
     reinvestment:
       execution:
         model: bacherlier_deepseek
   ```

   `execution.output`, `execution.logging`, and every other sibling key are
   inherited unchanged by the deep merge.

3. Supply the provider's API key. `bacherlier_deepseek` uses the `bacherlier`
   provider, whose key is read from `BACHERLIER_API_KEY`. Add it to `.env` and
   forward it in `compose.yaml`'s `environment:` list:

   ```dotenv
   # .env
   BACHERLIER_API_KEY=<your_key>
   ```

   ```yaml
   # compose.yaml → services.proposal-server.environment
   - BACHERLIER_API_KEY=${BACHERLIER_API_KEY:-}
   ```

4. Restart to apply:

   ```bash
   docker compose up -d
   ```

   The container re-reads `config-override/` on every start, so later changes
   only need a restart (`docker compose up -d`), not a rebuild.

The `provider` under each `llm_models` entry must match a key in
`config/config.yaml`'s `providers` section (`bacherlier`, `deepseek`, `poe`,
`openrouter`, or `mock`). You can override an existing entry (e.g. change its
`model` or `temperature`) or add a new one — both are shown above.

**Change a provider (base URL / API key).** A model's `provider` value (set
under `llm_models` in `config_planbot.yaml`) selects the matching entry in
`config/config.yaml`'s `providers` section, which carries the `base_url`,
`api_key_env`, and `timeout_seconds`. The full chain is:

```text
pipeline.<id>.execution.model   (config_planbot.yaml — which model a pipeline uses)
  └─ llm_models.<key>            (config_planbot.yaml — provider + model + temperature)
       └─ providers.<provider>    (config.yaml — api_key_env + base_url + timeout_seconds)
```

To repoint a provider at a different URL/gateway, override `config.yaml` with a
second override file — see
[`config-override/config.yaml.example`](config-override/config.yaml.example):

1. Activate it:

   ```bash
   cp config-override/config.yaml.example \
      config-override/config.yaml
   ```

2. Change `base_url` (and/or `api_key_env`) for the provider:

   ```yaml
   providers:
     bacherlier:
       api_key_env: BACHERLIER_API_KEY
       base_url: https://gateway.example.com/v1   # was the Aliyun MaaS endpoint
       timeout_seconds: 300
   ```

3. To point a model at a brand-new provider (e.g. a self-hosted gateway),
   register it in `config.yaml` and reference it from
   `config_planbot.yaml`:

   ```yaml
   # config-override/config.yaml
   providers:
     bacherlier_gateway:
       api_key_env: BACHERLIER_API_KEY
       base_url: https://bacherlier-gateway.example.com/v1
       timeout_seconds: 300
   ```

   ```yaml
   # config-override/config_planbot.yaml
   llm_models:
     bacherlier_via_gateway:
       provider: bacherlier_gateway
       model: deepseek-v4-flash-0731
       temperature: 0.1
   pipeline:
     product_opportunity:
       execution:
         model: bacherlier_via_gateway
   ```

4. Restart to apply:

   ```bash
   docker compose up -d
   ```

**Example — point the proposal server at the client's own data service:**

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

