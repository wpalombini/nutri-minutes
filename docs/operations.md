# Operations

How the pipeline runs in production with Docker Compose. The same setup also runs locally for development. Everything is defined in `compose.yaml` at the repo root, with settings and secrets in `.env` (see `.env.example`).

## Services

| Service | What it does | Runs |
|---|---|---|
| `db` | Postgres 17, with data in the `db-data` volume. Published on `127.0.0.1` only. | Always |
| `migrate` | Applies Alembic migrations as the schema owner, then exits | On every `up`, before the workers |
| `db-roles` | Creates or updates the `pipeline_runner` and `api_runner` login roles from `infra/postgres/login-roles.sql`, then exits. Both passwords are required by Compose. Run outside Compose, the script skips `api_runner` when its password is empty. | After `migrate` |
| `scheduler` | Runs `workers/crontab` with [supercronic](https://github.com/aptible/supercronic). Scout runs daily at 03:15 UTC. | Always |
| `scout` | One-off Scout runs. It's in the `manual` profile, so `up` doesn't start it. | On demand |
| `api` | The HTTP API for the web app ([ADR 0003](adr/0003-database-api-for-the-web-app.md)). It publishes no ports, runs with a read-only filesystem and no Linux capabilities, and checks a Cloudflare Access token on every `/v1` request. It also limits each client to `API_RATE_LIMIT_PER_MINUTE` requests (600 by default). | Always |
| `cloudflared` | Opens an outbound [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/) and forwards `api.nutriminutes.com` to `api`. The route is configured on the `research-api` tunnel in Cloudflare; `CLOUDFLARE_TUNNEL_TOKEN` only identifies this connector. | Always, after `api` is healthy |

The workers connect as `pipeline_runner`, which is a member of `pipeline_worker`, so they can read and write data but can't change the schema. Only `migrate` uses the owner role. The API connects as `api_runner`, which has no access to the pipeline tables yet; it gets read access to published views when they're added. Both images run as non-root users and build for `linux/amd64` and `linux/arm64`.

## First deploy on the VM
1. Install Docker with the Compose plugin, and clone the repo.
2. Copy `.env.example` to `.env`. Set `POSTGRES_PASSWORD`, `WORKER_DB_PASSWORD` and `API_DB_PASSWORD` to long random values made of letters and digits, such as the output of `openssl rand -hex 32`. Keep `.env` readable only by the deploy user (`chmod 600 .env`). `POSTGRES_PASSWORD` only takes effect when the database volume is first created; to change it later, change the role's password in Postgres too. `WORKER_DB_PASSWORD` and `API_DB_PASSWORD` can be changed at any time, and the next `up` applies them. Set `ACCESS_TEAM_DOMAIN` and `ACCESS_AUD` from the API's Access application, and `CLOUDFLARE_TUNNEL_TOKEN` from the `research-api` tunnel (see "Cloudflare setup").
3. Run `docker compose up -d --build`.
4. Check the services with `docker compose ps -a`. `migrate` and `db-roles` should show `Exited (0)`, and `db` and `scheduler` should be up. `api` should show `healthy` and `cloudflared` should be up. `docker compose logs cloudflared` should show registered tunnel connections.

## Everyday tasks
- **Deploy a change:** `git pull`, then `docker compose up -d --build`. Migrations run before the scheduler restarts.
- **Logs:** `docker compose logs -f scheduler`. Scout's alerts are log lines starting with `ALERT`. Logs rotate at 5 files of 10 MB per service.
- **Run Scout now:** `docker compose run --rm scout`.
- **Re-run a past window:** `docker compose run --rm scout --window-start YYYY-MM-DD --window-end YYYY-MM-DD`.
- **API checks:** `docker compose exec api node -e "fetch('http://127.0.0.1:3000/readyz').then(async (r) => console.log(r.status, await r.text()))"`. `/healthz` reports the process is up and `/readyz` that the database answers. Neither needs a token.
- **Database shell:** `docker compose exec db psql -U pipeline pipeline`.
- **Dependency updates:** Dependabot opens weekly PRs for npm and uv packages, base images and pinned actions, 14 days after each release. They go through the normal review. Two pins must be updated by hand: the Postgres service image in `.github/workflows/workers.yml`, to match `compose.yaml`, and the `setup-uv` `version` there, to match the uv image in `workers/Dockerfile`.
- **Login roles test:** CI checks `infra/postgres/login-roles.sql` with `infra/postgres/test-login-roles.sh`. Roles are server-wide, so the script refuses to run outside CI unless `ALLOW_SERVER_ROLE_CHANGES=1` is set; never run it against the stack's database server.
- **Change the schedule:** edit `workers/crontab` (times are UTC), then redeploy.
- **Project mail:** `contact@nutriminutes.com` is the contact address Scout sends to Europe PMC. Cloudflare Email Routing forwards it to the owner's inbox, so manage it in the Cloudflare dashboard under Email Routing.

## Cloudflare setup
The API is published as `api.nutriminutes.com`:
- **Tunnel:** `research-api`, managed in Cloudflare (Networks > Tunnels). Its public hostname route sends `api.nutriminutes.com` to `http://api:3000`, and everything else to 404.
- **Access application:** a self-hosted application for `api.nutriminutes.com` whose only policy is Service Auth, allowing only the web app's service token. Its AUD tag goes in `ACCESS_AUD`, and the team domain in `ACCESS_TEAM_DOMAIN`.
- **Service token:** the web app sends its `CF-Access-Client-Id` and `CF-Access-Client-Secret` on every request. The secret is shown once, when the token is created, and belongs in the web app's environment, not in this repo or `.env`.
- **Rate limiting:** a Cloudflare rate limiting rule on the API hostname, then the API's own per-client limit.

To check from outside, with the service token: `curl -H "CF-Access-Client-Id: $ID" -H "CF-Access-Client-Secret: $SECRET" https://api.nutriminutes.com/v1/ping` should return `{"status":"ok"}`. Without the headers, Access rejects the request before it reaches the VM.

## Not covered yet
- **Token rotation runbook:** rotating the Access service token and the tunnel token (ADR 0003) isn't written up yet.
- **API with wrong settings:** with a wrong `API_DB_PASSWORD` the API stays up but `/readyz` reports 503. With invalid Access settings, it exits and restarts in a loop. Check `docker compose logs api`.
- **Backups:** the database volume isn't backed up yet. Add this before the data matters.
- **Alerts outside the logs:** alerts only go to the logs until the Discord notifier is added.
- **Secrets:** passwords are passed as environment variables, so anyone who can run `docker inspect` on the VM can read them. Limit Docker access to the deploy user.
