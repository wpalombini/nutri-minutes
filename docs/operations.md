# Operations

How the pipeline runs in production with Docker Compose. The same setup also runs locally for development. Everything is defined in `compose.yaml` at the repo root, with settings and secrets in `.env` (see `.env.example`).

## Services

| Service | What it does | Runs |
|---|---|---|
| `db` | Postgres 17, with data in the `db-data` volume. Published on `127.0.0.1` only. | Always |
| `migrate` | Applies Alembic migrations as the schema owner, then exits | On every `up`, before the workers |
| `db-roles` | Creates or updates the `pipeline_runner` and `api_runner` login roles from `infra/postgres/login-roles.sql`, then exits. `api_runner` is skipped when `API_DB_PASSWORD` is empty; clearing it later leaves the role with its old password, so disable it in Postgres if that's the intent. | After `migrate` |
| `scheduler` | Runs `workers/crontab` with [supercronic](https://github.com/aptible/supercronic). Scout runs daily at 03:15 UTC. | Always |
| `scout` | One-off Scout runs. It's in the `manual` profile, so `up` doesn't start it. | On demand |
| `api` | The HTTP API for the web app ([ADR 0003](adr/0003-database-api-for-the-web-app.md)). It publishes no ports, runs with a read-only filesystem and no Linux capabilities, and checks a Cloudflare Access token on every `/v1` request. It's in the `api` profile until the Cloudflare tunnel is added. | `docker compose --profile api up -d` |

The workers connect as `pipeline_runner`, which is a member of `pipeline_worker`, so they can read and write data but can't change the schema. Only `migrate` uses the owner role. The API connects as `api_runner`, which has no access to the pipeline tables yet; it gets read access to published views when they're added. Both images run as non-root users and build for `linux/amd64` and `linux/arm64`.

## First deploy on the VM
1. Install Docker with the Compose plugin, and clone the repo.
2. Copy `.env.example` to `.env`. Set `POSTGRES_PASSWORD`, `WORKER_DB_PASSWORD` and `API_DB_PASSWORD` to long random values made of letters and digits, such as the output of `openssl rand -hex 32`. Keep `.env` readable only by the deploy user (`chmod 600 .env`). `POSTGRES_PASSWORD` only takes effect when the database volume is first created; to change it later, change the role's password in Postgres too. `WORKER_DB_PASSWORD` and `API_DB_PASSWORD` can be changed at any time, and the next `up` applies them. Set `ACCESS_TEAM_DOMAIN` and `ACCESS_AUD` from the API's Cloudflare Access application once it exists.
3. Run `docker compose up -d --build`.
4. Check the services with `docker compose ps -a`. `migrate` and `db-roles` should show `Exited (0)`, and `db` and `scheduler` should be up. With `--profile api`, `api` should show `healthy`.

## Everyday tasks
- **Deploy a change:** `git pull`, then `docker compose up -d --build`. Migrations run before the scheduler restarts.
- **Logs:** `docker compose logs -f scheduler`. Scout's alerts are log lines starting with `ALERT`. Logs rotate at 5 files of 10 MB per service.
- **Run Scout now:** `docker compose run --rm scout`.
- **Re-run a past window:** `docker compose run --rm scout --window-start YYYY-MM-DD --window-end YYYY-MM-DD`.
- **API checks:** `docker compose exec api node -e "fetch('http://127.0.0.1:3000/readyz').then(async (r) => console.log(r.status, await r.text()))"`. `/healthz` reports the process is up and `/readyz` that the database answers. Neither needs a token.
- **Database shell:** `docker compose exec db psql -U pipeline pipeline`.
- **Change the schedule:** edit `workers/crontab` (times are UTC), then redeploy.
- **Project mail:** `contact@nutriminutes.com` is the contact address Scout sends to Europe PMC. Cloudflare Email Routing forwards it to the owner's inbox, so manage it in the Cloudflare dashboard under Email Routing.

## Not covered yet
- **Public access to the API:** the Cloudflare tunnel and Access application aren't set up yet, so nothing outside the VM can reach the API. Rate limiting and the service token rotation runbook (ADR 0003) come with them.
- **API with missing settings:** with `API_DB_PASSWORD` empty, the API stays up but `/readyz` reports 503. With the Access settings missing, it exits and restarts in a loop. Check `docker compose logs api`.
- **Backups:** the database volume isn't backed up yet. Add this before the data matters.
- **Alerts outside the logs:** alerts only go to the logs until the Discord notifier is added.
- **Secrets:** passwords are passed as environment variables, so anyone who can run `docker inspect` on the VM can read them. Limit Docker access to the deploy user.
