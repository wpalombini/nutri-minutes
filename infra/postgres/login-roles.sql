-- Creates or updates the login roles the pipeline workers and the API connect as. Idempotent, and
-- run by the db-roles service after migrations, which create the pipeline_worker group role.
-- Requires psql variables worker_password and api_password. The API role is skipped when
-- api_password is empty.

\set ON_ERROR_STOP on

-- Keep passwords out of the server log. A failing statement is normally logged with its text,
-- which here would include a password. Both settings need a superuser, which the schema owner
-- is in the Compose stack.
SET log_min_error_statement = panic;
SET log_statement = 'none';

SELECT 'CREATE ROLE pipeline_runner LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pipeline_runner')
\gexec

ALTER ROLE pipeline_runner WITH LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
    PASSWORD :'worker_password';
GRANT pipeline_worker TO pipeline_runner;

-- The API's login role (ADR 0003). It gets no grants yet: its group role, which can read published
-- views only, is added by the migration that creates the first view.
SELECT :'api_password' <> '' AS create_api_role
\gset
\if :create_api_role
SELECT 'CREATE ROLE api_runner LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'api_runner')
\gexec

ALTER ROLE api_runner WITH LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
    CONNECTION LIMIT 10 PASSWORD :'api_password';
\else
\echo 'API_DB_PASSWORD is not set, so the api_runner role was not created or updated.'
\endif
