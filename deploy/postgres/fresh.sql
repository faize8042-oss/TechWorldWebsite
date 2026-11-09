-- FRESH EMPTY DATABASE ONLY. Manual psql review/execution; never auto-mounted.
-- Fixed identifiers are intentional: no untrusted identifier interpolation.
-- Connect as cv_init to codeventra; use psql -X -v ON_ERROR_STOP=1.
BEGIN;
DO $$
BEGIN
  IF current_database() <> 'codeventra' OR session_user <> 'cv_init' THEN
    RAISE EXCEPTION 'Unexpected provisioning target';
  END IF;
  IF EXISTS (SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
               AND n.nspname !~ '^pg_toast' AND n.nspname !~ '^pg_temp')
     OR EXISTS (SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname='public') THEN
    RAISE EXCEPTION 'Fresh provisioning requires an empty database';
  END IF;
END $$;
CREATE ROLE cv_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE cv_migrate LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD NULL;
CREATE ROLE cv_runtime LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD NULL;
CREATE ROLE cv_backup LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD NULL;
GRANT cv_owner TO cv_migrate WITH INHERIT FALSE, SET TRUE, ADMIN FALSE;
ALTER SCHEMA public OWNER TO cv_owner;
COMMIT;
-- Repeatable ACL reconciliation is separate; run grants.sql next.
-- Existing roles intentionally cause failure. Never catch duplicate_object here.
-- Set SCRAM passwords privately using psql \password, never SQL literals or -v.
