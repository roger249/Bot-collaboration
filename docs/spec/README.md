# Planbot Proposal Server Deployment Guide

This guide is intended for GitHub readers who need to:

1. Deploy on Linux.
2. Test proposal APIs from Swagger.

For image build and publish instructions, see [docs/spec/dockerization.md](dockerization.md).

## 1. Deploy on Linux (AMD64)

From repository root on Linux:

1. Pull latest repository changes.
2. Export secrets.
3. Edit top settings in [docker/deploy_linux.sh](../../docker/deploy_linux.sh).
4. Run deployment script.

```bash
git pull
export GHCR_TOKEN="your_ghcr_token"
export DEEPSEEK_API_KEY="your_real_key_here"
./docker/deploy_linux.sh
```

Edit these script settings once:

1. `GHCR_OWNER`
2. `IMAGE_NAME`
3. `IMAGE_TAG`
4. `ENV_FILE`

The deploy script will:

1. Validate required variables.
2. Generate `.env` for compose.
3. Login to GHCR.
4. Pull the pinned image.
5. Start `proposal-server`.

## 2. Verify Deployment Health

```bash
docker compose ps
docker compose logs --tail=200 proposal-server
curl -f http://localhost:8000/docs >/dev/null && echo "docs ok"
curl -f http://localhost:8000/openapi.json >/dev/null && echo "openapi ok"
```

## 3. Test Proposal API in Swagger

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

## 4. Upgrade to a New Image Version

1. Obtain the new release `IMAGE_TAG` from the build/publish pipeline.
2. Update `IMAGE_TAG` in [docker/deploy_linux.sh](../../docker/deploy_linux.sh).
3. Redeploy:

```bash
git pull
export GHCR_TOKEN="your_ghcr_token"
export DEEPSEEK_API_KEY="your_real_key_here"
./docker/deploy_linux.sh
```

