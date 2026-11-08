#!/usr/bin/env bash
# Checks infra/postgres/login-roles.sql against a disposable database: it creates both roles, can
# be run again, skips the API role without a password, and leaves the API role with no access to
# pipeline tables. Needs psql, and TEST_DATABASE_URL pointing at a database whose schema is at the
# latest migration (CI runs this after the workers' tests, then migrates). The schema check
# assumes public was recreated without the default USAGE grant to PUBLIC, as the workers'
# test setup does.
#
# Roles belong to the whole Postgres server, not one database, so this changes the passwords of
# pipeline_runner and api_runner for every database on that server. It runs only in CI unless
# ALLOW_SERVER_ROLE_CHANGES=1 is set. Don't point it at a server other services depend on.
set -euo pipefail

: "${TEST_DATABASE_URL:?Set TEST_DATABASE_URL}"
if [ "${CI:-}" != "true" ] && [ "${ALLOW_SERVER_ROLE_CHANGES:-}" != "1" ]; then
  echo "Refusing to run outside CI: it changes server-wide role passwords." >&2
  echo "Set ALLOW_SERVER_ROLE_CHANGES=1 to run it against a disposable server." >&2
  exit 2
fi
script_dir="$(cd "$(dirname "$0")" && pwd)"
roles_sql="$script_dir/login-roles.sql"

(cd "$script_dir/../../workers" && DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head)

run_roles() {
  psql "$TEST_DATABASE_URL" -q -v worker_password="$1" -v api_password="$2" -f "$roles_sql"
}
query() {
  psql "$TEST_DATABASE_URL" -Atq -c "$1"
}
fail() {
  echo "FAIL: $1" >&2
  exit 1
}

query "DROP ROLE IF EXISTS api_runner"

skipped_output="$(run_roles "worker-ci-1" "")"
grep -q "api_runner role was not created" <<<"$skipped_output" || fail "empty api_password should skip api_runner"
[ "$(query "SELECT count(*) FROM pg_roles WHERE rolname = 'api_runner'")" = 0 ] || fail "api_runner created without a password"

run_roles "worker-ci-1" "api-ci-1"
run_roles "worker-ci-2" "api-ci-2"  # Idempotent, and updates passwords.

[ "$(query "SELECT rolconnlimit FROM pg_roles WHERE rolname = 'api_runner'")" = 10 ] || fail "api_runner connection limit"
[ "$(query "SELECT pg_has_role('pipeline_runner', 'pipeline_worker', 'MEMBER')")" = t ] || fail "pipeline_runner not in pipeline_worker"
[ "$(query "SELECT pg_has_role('api_runner', 'pipeline_worker', 'MEMBER')")" = f ] || fail "api_runner must not be in pipeline_worker"
[ "$(query "SELECT has_schema_privilege('api_runner', 'public', 'USAGE')")" = f ] || fail "api_runner can use schema public"
for table in articles article_licences article_relations pipeline_runs pipeline_run_errors; do
  [ "$(query "SELECT has_table_privilege('api_runner', 'public.$table', 'SELECT')")" = f ] || fail "api_runner can read $table"
done

# The passwords set last must work for login.
url_for() {
  python3 - "$TEST_DATABASE_URL" "$1" "$2" <<'PY'
import sys
from urllib.parse import quote, urlsplit

url, user, password = sys.argv[1:]
parts = urlsplit(url)
host = f"[{parts.hostname}]" if ":" in (parts.hostname or "") else parts.hostname
netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{host}:{parts.port or 5432}"
print(parts._replace(netloc=netloc).geturl())
PY
}
psql "$(url_for pipeline_runner worker-ci-2)" -Atqc "SELECT 1" >/dev/null || fail "pipeline_runner login"
psql "$(url_for api_runner api-ci-2)" -Atqc "SELECT 1" >/dev/null || fail "api_runner login"

echo "login-roles.sql checks passed"
