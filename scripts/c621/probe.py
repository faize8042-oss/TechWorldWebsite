"""Container-only synthetic tests. Exceptions never escape with connection details."""
import json
import os
from pathlib import Path
import stat
import sys

SECRETS = Path('/run/secrets')


def require(condition):
    if not condition:
        raise AssertionError('Validation assertion failed')


def write_secret(name, value):
    path = SECRETS / name
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream)


def seed(service):
    values = json.load(sys.stdin)
    require(stat.S_IMODE(SECRETS.stat().st_mode) == 0o700)
    if service == 'audit':
        write_secret('audit', values)
        return
    runtime = {
        'DATABASE_URL': 'postgresql://cv_runtime:' + values['runtime'] + '@db:5432/codeventra',
        'SECRET_KEY': 'synthetic-validation-only-' + values['runtime'],
        'ALLOWED_HOSTS': 'site.example', 'CSRF_TRUSTED_ORIGINS': 'https://site.example',
        # Redis is intentionally excluded; this URL is parsed but never connected.
        'REDIS_URL': 'redis://:synthetic-not-used@redis:6379/0',
        'CONTACT_EMAIL': 'test@example.invalid', 'DEFAULT_FROM_EMAIL': 'test@example.invalid',
        'EMAIL_HOST': 'smtp.example.invalid', 'EMAIL_HOST_USER': 'synthetic',
        'EMAIL_HOST_PASSWORD': 'synthetic',
    }
    write_secret('django_runtime', runtime)
    if service == 'migrate':
        write_secret('django_migration', {'DATABASE_URL':
            'postgresql://cv_migrate:' + values['migration'] + '@db:5432/codeventra'})


def permissions(expected):
    require({p.name for p in SECRETS.iterdir()} == set(expected))
    require(stat.S_IMODE(SECRETS.stat().st_mode) == 0o700)
    for name in expected:
        path = SECRETS / name
        require(path.is_file() and not path.is_symlink())
        require(stat.S_IMODE(path.stat().st_mode) == 0o600)
        require(path.stat().st_uid == os.getuid() == 10001)


def connect(role):
    import psycopg
    credentials = json.loads((SECRETS / 'audit').read_text())
    return psycopg.connect(host='db', port=5432, dbname='codeventra', user=role,
                          password=credentials[role], connect_timeout=5, autocommit=True)


def denied(connection, sql, state='42501'):
    import psycopg
    try:
        connection.execute(sql)
    except psycopg.Error as error:
        require(error.sqlstate == state)
    else:
        raise AssertionError('Expected denial missing')


def scalar(connection, sql):
    return connection.execute(sql).fetchone()[0]


def sql_tests():
    permissions(['audit'])
    with connect('cv_init') as admin, connect('cv_migrate') as migration:
        require(scalar(admin, 'SHOW server_version_num').startswith('17'))
        require(scalar(admin, "SELECT count(*) FROM pg_roles WHERE rolname IN ('cv_owner','cv_migrate','cv_runtime','cv_backup') AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)") == 0)
        require(scalar(admin, "SELECT count(*) FROM pg_roles WHERE rolname='cv_owner' AND NOT rolcanlogin") == 1)
        require(scalar(admin, "SELECT count(*) FROM pg_roles WHERE rolname IN ('cv_migrate','cv_runtime','cv_backup') AND rolcanlogin AND NOT rolinherit") == 3)
        require(scalar(admin, "SELECT count(*) FROM pg_auth_members WHERE member IN ('cv_owner'::regrole,'cv_runtime'::regrole,'cv_backup'::regrole)") == 0)
        require(scalar(admin, "SELECT count(*) FROM pg_auth_members WHERE member='cv_migrate'::regrole") == 1)
        require(scalar(admin, "SELECT count(*) FROM pg_auth_members WHERE member='cv_migrate'::regrole AND roleid='cv_owner'::regrole AND NOT inherit_option AND set_option AND NOT admin_option") == 1)
        denied(migration, 'CREATE TABLE public.c621_unassumed(id int)')
        migration.execute('SET ROLE cv_owner')
        require(migration.execute('SELECT session_user,current_user').fetchone() == ('cv_migrate', 'cv_owner'))
        migration.execute('''CREATE TABLE public.c621_existing(id bigserial PRIMARY KEY, value text);
CREATE TYPE public.c621_existing_type AS (value text);
CREATE FUNCTION public.c621_existing_function() RETURNS integer LANGUAGE sql AS 'SELECT 42';
CREATE PROCEDURE public.c621_definer() LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,public AS 'INSERT INTO public.c621_existing(value) VALUES (''definer'')';
GRANT EXECUTE ON FUNCTION public.c621_existing_function() TO PUBLIC, cv_runtime, cv_backup;
GRANT EXECUTE ON PROCEDURE public.c621_definer() TO PUBLIC, cv_runtime, cv_backup;
GRANT USAGE ON TYPE public.c621_existing_type TO PUBLIC, cv_migrate;
GRANT ALL ON TABLE public.c621_existing TO cv_runtime, cv_backup;
GRANT ALL ON SEQUENCE public.c621_existing_id_seq TO cv_runtime, cv_backup;''', prepare=False)
        # Existing object reconciliation, including stale standalone composite/routine ACLs.
        admin.execute(Path('/work/deploy/postgres/grants.sql').read_text(), prepare=False)
        migration.execute('''CREATE TABLE public.c621_future(id bigserial PRIMARY KEY, value text);
CREATE TYPE public.c621_future_type AS (value text);
CREATE FUNCTION public.c621_future_function() RETURNS integer LANGUAGE sql AS 'SELECT 42';
CREATE PROCEDURE public.c621_future_procedure() LANGUAGE sql AS 'SELECT 42';''', prepare=False)
        with connect('cv_runtime') as runtime, connect('cv_backup') as backup:
            require(scalar(backup, 'SHOW default_transaction_read_only') == 'on')
            backup.execute('SET default_transaction_read_only=off')  # ACLs must still enforce read-only.
            for table in ('c621_existing', 'c621_future'):
                runtime.execute(f"INSERT INTO public.{table}(value) VALUES ('synthetic')")
                runtime.execute(f"UPDATE public.{table} SET value='changed'")
                require(scalar(runtime, f'SELECT count(*) FROM public.{table}') == 1)
                require(scalar(backup, f'SELECT count(*) FROM public.{table}') == 1)
                require(scalar(backup, f'SELECT last_value FROM public.{table}_id_seq') >= 1)
                for statement in (f"INSERT INTO public.{table}(value) VALUES ('no')",
                                  f"UPDATE public.{table} SET value='no'", f'DELETE FROM public.{table}',
                                  f"SELECT nextval('public.{table}_id_seq')",
                                  f"SELECT setval('public.{table}_id_seq',10)"):
                    denied(backup, statement)
                for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE'):
                    require(scalar(admin, f"SELECT has_table_privilege('cv_runtime','public.{table}','{privilege}')"))
                for privilege in ('TRUNCATE', 'REFERENCES', 'TRIGGER', 'MAINTAIN'):
                    require(not scalar(admin, f"SELECT has_table_privilege('cv_runtime','public.{table}','{privilege}')"))
                require(scalar(admin, f"SELECT has_sequence_privilege('cv_runtime','public.{table}_id_seq','USAGE,SELECT')"))
                require(not scalar(admin, f"SELECT has_sequence_privilege('cv_runtime','public.{table}_id_seq','UPDATE')"))
                runtime.execute(f'DELETE FROM public.{table}')
            for connection in (runtime, backup):
                for statement in ('CREATE TABLE public.c621_denied(id int)', 'CREATE SCHEMA c621_denied',
                                  'CREATE TEMP TABLE c621_denied(id int)', 'SET ROLE cv_owner',
                                  'SET ROLE cv_migrate', 'SET ROLE cv_init', 'CREATE ROLE c621_denied',
                                  'ALTER ROLE cv_runtime SUPERUSER', 'GRANT cv_owner TO cv_runtime',
                                  'TRUNCATE public.c621_existing', 'DROP TABLE public.c621_existing',
                                  'ALTER TABLE public.c621_existing ADD COLUMN denied int',
                                  'SELECT public.c621_existing_function()', 'SELECT public.c621_future_function()',
                                  'CALL public.c621_definer()', 'CALL public.c621_future_procedure()'):
                    denied(connection, statement)
                for typename in ('c621_existing_type', 'c621_future_type'):
                    require(scalar(admin, f"SELECT has_type_privilege('{connection.info.user}','public.{typename}','USAGE')"))
                    require(not scalar(admin, f"SELECT EXISTS(SELECT FROM pg_type t CROSS JOIN LATERAL aclexplode(t.typacl) a WHERE t.oid='public.{typename}'::regtype AND a.grantee=0)"))
            require(not scalar(admin, "SELECT has_type_privilege('cv_migrate','public.c621_existing_type','USAGE')"))
            # Explicitly reviewed procedure grant; SQL SECURITY DEFINER cannot commit internally.
            migration.execute('REVOKE INSERT ON public.c621_existing FROM cv_runtime')
            denied(runtime, "INSERT INTO public.c621_existing(value) VALUES ('denied')")
            migration.execute('GRANT EXECUTE ON PROCEDURE public.c621_definer() TO cv_runtime')
            runtime.execute('CALL public.c621_definer()')
            require(scalar(runtime, "SELECT count(*) FROM public.c621_existing WHERE value='definer'") == 1)
            migration.execute("CREATE PROCEDURE public.c621_definer_commit() LANGUAGE plpgsql SECURITY DEFINER AS 'BEGIN COMMIT; END'; GRANT EXECUTE ON PROCEDURE public.c621_definer_commit() TO cv_runtime;", prepare=False)
            denied(runtime, 'CALL public.c621_definer_commit()', '2D000')
            migration.execute('REVOKE EXECUTE ON PROCEDURE public.c621_definer_commit() FROM cv_runtime')
            migration.execute('GRANT INSERT ON public.c621_existing TO cv_runtime')
            migration.execute('REVOKE EXECUTE ON PROCEDURE public.c621_definer() FROM cv_runtime')
            denied(runtime, 'CALL public.c621_definer()')
        # Owner cannot acquire database-level CREATE or TEMP privileges either.
        denied(migration, 'CREATE SCHEMA c621_owner_denied')
        migration.execute('RESET ROLE')
        denied(migration, 'CREATE TABLE public.c621_after_reset(id int)')
    # Reconnect must require migration SET ROLE again on a raw connection.
    with connect('cv_migrate') as migration:
        require(scalar(migration, 'SELECT current_user') == 'cv_migrate')


def configure(migration=False):
    os.environ.update(DEPLOYMENT_MODE='production', DEBUG='False', ENABLE_HTTPS='True',
                      PRODUCTION_PROXY_TRANSPORT='unix', PRODUCTION_RUNTIME_FILE='/run/secrets/django_runtime',
                      DJANGO_SETTINGS_MODULE='config.migration_settings' if migration else 'config.settings')
    import django
    django.setup()


def django_migrate():
    permissions(['django_runtime', 'django_migration'])
    configure(True)
    from django.core.management import call_command
    from django.db import connection
    for _ in range(2):
        with connection.cursor() as cursor:
            cursor.execute('SELECT session_user,current_user')
            require(cursor.fetchone() == ('cv_migrate', 'cv_owner'))
        connection.close()
    # All repository migrations, on this run's empty synthetic database only.
    with open(os.devnull, 'w') as output:
        call_command('migrate', interactive=False, skip_checks=True, verbosity=0, stdout=output, stderr=output)


def django_web():
    permissions(['django_runtime'])
    raw = (SECRETS / 'django_runtime').read_text()
    require(all(marker not in raw for marker in ('cv_init', 'cv_migrate', 'cv_backup', 'POSTGRES_', 'MIGRATION_', 'BACKUP_')))
    require(not any(k.startswith(('POSTGRES_', 'MIGRATION_', 'BACKUP_', 'PG')) for k in os.environ))
    configure()
    from django.core.management import call_command
    from django.db import connection, DatabaseError
    from django.db.migrations.recorder import MigrationRecorder
    from django.contrib.contenttypes.models import ContentType
    for _ in range(2):
        with connection.cursor() as cursor:
            cursor.execute('SELECT session_user,current_user')
            require(cursor.fetchone() == ('cv_runtime', 'cv_runtime'))
        item = ContentType.objects.create(app_label='c621_synthetic', model='probe')
        require(ContentType.objects.filter(pk=item.pk).exists())
        item.model = 'changed'
        item.save()
        item.delete()
        connection.close()
    # A normal migrate on an up-to-date schema is a no-op, so force genuine DDL via
    # a fresh recorder table name, then require insufficient_privilege specifically.
    old_table = MigrationRecorder.Migration._meta.db_table
    MigrationRecorder.Migration._meta.db_table = 'c621_runtime_migration_denied'
    try:
        with open(os.devnull, 'w') as output:
            call_command('migrate', interactive=False, skip_checks=True, verbosity=0, stdout=output, stderr=output)
    except Exception as error:
        cause = error
        while cause.__cause__ is not None or cause.__context__ is not None:
            cause = cause.__cause__ or cause.__context__
        require(getattr(cause, 'sqlstate', None) == '42501')
    else:
        raise AssertionError('Runtime migration unexpectedly succeeded')
    finally:
        MigrationRecorder.Migration._meta.db_table = old_table
    # Recorder raises MigrationSchemaMissing wrapping DatabaseError on supported Django.
    # The outer dispatch checks the same chain if that wrapper occurs.
    with connection.cursor() as cursor:
        try:
            cursor.execute('CREATE TABLE public.c621_web_denied(id int)')
        except DatabaseError as error:
            require(getattr(error.__cause__, 'sqlstate', None) == '42501')
        else:
            raise AssertionError('Runtime DDL unexpectedly allowed')


def ownership():
    permissions(['audit'])
    with connect('cv_init') as admin:
        require(scalar(admin, "SELECT count(*) FROM public.django_migrations") > 0)
        require(scalar(admin, "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relowner <> 'cv_owner'::regrole") == 0)
        require(scalar(admin, "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proowner <> 'cv_owner'::regrole") == 0)
        require(scalar(admin, "SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public' AND t.typowner <> 'cv_owner'::regrole") == 0)
        require(scalar(admin, "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public'") == 'cv_owner')
        require(scalar(admin, "SELECT to_regclass('public.c621_runtime_migration_denied') IS NULL"))
        require(scalar(admin, "SELECT has_table_privilege('cv_runtime','public.django_migrations','SELECT,INSERT,UPDATE,DELETE')"))


def main():
    try:
        mode = sys.argv[1]
        if mode == 'seed':
            seed(sys.argv[2])
        else:
            {'sql': sql_tests, 'migrate': django_migrate, 'web': django_web, 'ownership': ownership}[mode]()
        print('PASS: synthetic validation phase')
        return 0
    except Exception:
        print('FAIL: synthetic validation phase; details suppressed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
