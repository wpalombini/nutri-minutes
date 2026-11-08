-- Creates or updates the login role the pipeline workers connect as. Idempotent, and run by the
-- db-roles service after migrations, which create the pipeline_worker group role.
-- Requires psql variable worker_password.

\set ON_ERROR_STOP on

SELECT 'CREATE ROLE pipeline_runner LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pipeline_runner')
\gexec

ALTER ROLE pipeline_runner WITH LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
    PASSWORD :'worker_password';
GRANT pipeline_worker TO pipeline_runner;
