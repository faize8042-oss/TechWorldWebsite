-- Reviewed ACL reconciliation, only after ownership inventory and approval.
-- Does NOT adopt objects, change existing ownership, passwords, or memberships.
-- Connect cv_init/codeventra; psql -X -v ON_ERROR_STOP=1.
BEGIN;
DO $$
BEGIN
  IF current_database() <> 'codeventra' OR session_user <> 'cv_init'
     OR (SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public') <> 'cv_owner'
     OR EXISTS (SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relowner <> 'cv_owner'::regrole)
     OR EXISTS (SELECT FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
                WHERE n.nspname='public' AND t.typowner <> 'cv_owner'::regrole)
     OR EXISTS (SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname='public' AND p.proowner <> 'cv_owner'::regrole) THEN
    RAISE EXCEPTION 'Target or ownership mismatch: stop for inventory';
  END IF;
  IF (SELECT count(*) FROM pg_roles WHERE rolname IN ('cv_owner','cv_runtime','cv_migrate','cv_backup')) <> 4
     OR EXISTS (SELECT FROM pg_roles WHERE rolname IN ('cv_owner','cv_runtime','cv_migrate','cv_backup')
                AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls
                     OR (rolname='cv_owner' AND rolcanlogin)
                     OR (rolname<>'cv_owner' AND (NOT rolcanlogin OR rolinherit))))
     OR EXISTS (SELECT FROM pg_auth_members WHERE member IN ('cv_runtime'::regrole, 'cv_backup'::regrole, 'cv_owner'::regrole))
     OR (SELECT count(*) FROM pg_auth_members WHERE member='cv_migrate'::regrole) <> 1
     OR NOT EXISTS (SELECT FROM pg_auth_members WHERE member='cv_migrate'::regrole
                    AND roleid='cv_owner'::regrole AND NOT inherit_option AND set_option AND NOT admin_option)
     OR EXISTS (SELECT FROM pg_auth_members WHERE roleid='cv_owner'::regrole AND member<>'cv_migrate'::regrole) THEN
    RAISE EXCEPTION 'Role flags or memberships violate the approved contract';
  END IF;
END $$;
REVOKE ALL ON DATABASE codeventra FROM PUBLIC;
REVOKE ALL ON DATABASE codeventra FROM cv_runtime, cv_migrate, cv_backup, cv_owner;
GRANT CONNECT ON DATABASE codeventra TO cv_runtime, cv_migrate, cv_backup;
REVOKE ALL ON SCHEMA public FROM PUBLIC, cv_runtime, cv_migrate, cv_backup;
GRANT USAGE ON SCHEMA public TO cv_runtime, cv_backup;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, cv_runtime, cv_migrate, cv_backup;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, cv_runtime, cv_migrate, cv_backup;
REVOKE ALL ON ALL ROUTINES IN SCHEMA public FROM PUBLIC, cv_runtime, cv_migrate, cv_backup CASCADE;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cv_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cv_runtime;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO cv_backup;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO cv_backup;
-- No application routine EXECUTE grants are approved. Reconcile every explicit
-- non-owner grantee, including legacy roles; CASCADE removes delegated grants.
DO $$
DECLARE item record;
BEGIN
  FOR item IN SELECT DISTINCT a.grantee FROM pg_proc p
              JOIN pg_namespace n ON n.oid=p.pronamespace
              CROSS JOIN LATERAL aclexplode(p.proacl) a
              WHERE n.nspname='public' AND a.grantee <> 0 AND a.grantee <> p.proowner
  LOOP
    EXECUTE format('REVOKE ALL ON ALL ROUTINES IN SCHEMA public FROM %I CASCADE',
                   pg_get_userbyid(item.grantee));
  END LOOP;
END $$;
-- Existing custom types have a separate ACL; no ALL TYPES shorthand exists.
DO $$
DECLARE item record; recipient record;
BEGIN
  FOR item IN SELECT n.nspname, t.typname, t.typacl, t.typowner FROM pg_type t
              JOIN pg_namespace n ON n.oid=t.typnamespace
              LEFT JOIN pg_class c ON c.oid=t.typrelid
              WHERE n.nspname='public' AND t.typelem=0
                AND (t.typtype IN ('e','d','r','m','b')
                     OR (t.typtype='c' AND c.relkind='c'))
  LOOP
    FOR recipient IN SELECT DISTINCT grantee FROM aclexplode(item.typacl)
                     WHERE grantee <> 0 AND grantee <> item.typowner
    LOOP
      EXECUTE format('REVOKE ALL ON TYPE %I.%I FROM %I CASCADE',
                     item.nspname, item.typname, pg_get_userbyid(recipient.grantee));
    END LOOP;
    EXECUTE format('REVOKE ALL ON TYPE %I.%I FROM PUBLIC, cv_runtime, cv_migrate, cv_backup CASCADE', item.nspname, item.typname);
    EXECUTE format('GRANT USAGE ON TYPE %I.%I TO cv_runtime, cv_backup', item.nspname, item.typname);
  END LOOP;
END $$;
-- Unexpected owner defaults need individual inventory/review before reconciliation.
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_default_acl d
             CROSS JOIN LATERAL aclexplode(d.defaclacl) a
             WHERE d.defaclrole='cv_owner'::regrole AND d.defaclobjtype IN ('f','T')
               AND (d.defaclnamespace=0 OR d.defaclnamespace='public'::regnamespace)
               AND a.grantee NOT IN (0, 'cv_owner'::regrole, 'cv_runtime'::regrole,
                                     'cv_migrate'::regrole, 'cv_backup'::regrole)) THEN
    RAISE EXCEPTION 'Unapproved routine/type default grantee: inventory required';
  END IF;
END $$;
-- Defaults apply to current_role, not session_user or inherited memberships.
-- Django migration connections MUST SET ROLE cv_owner before any DDL.
-- Clear both global and schema-specific grants before rebuilding minimal defaults.
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner REVOKE ALL ON TABLES FROM cv_runtime, cv_migrate, cv_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner REVOKE ALL ON SEQUENCES FROM cv_runtime, cv_migrate, cv_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner REVOKE ALL ON ROUTINES FROM cv_runtime, cv_migrate, cv_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner REVOKE ALL ON TYPES FROM cv_runtime, cv_migrate, cv_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC, cv_runtime, cv_migrate, cv_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC, cv_runtime, cv_migrate, cv_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner IN SCHEMA public REVOKE ALL ON ROUTINES FROM PUBLIC, cv_runtime, cv_migrate, cv_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner IN SCHEMA public REVOKE ALL ON TYPES FROM PUBLIC, cv_runtime, cv_migrate, cv_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner REVOKE ALL ON SEQUENCES FROM PUBLIC;
-- Function EXECUTE and type USAGE have global PUBLIC defaults.
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner REVOKE EXECUTE ON ROUTINES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner REVOKE USAGE ON TYPES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cv_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO cv_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner IN SCHEMA public GRANT SELECT ON TABLES TO cv_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner IN SCHEMA public GRANT SELECT ON SEQUENCES TO cv_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner IN SCHEMA public GRANT USAGE ON TYPES TO cv_runtime, cv_backup;
ALTER ROLE cv_runtime IN DATABASE codeventra SET search_path = public;
ALTER ROLE cv_migrate IN DATABASE codeventra SET search_path = public;
ALTER ROLE cv_backup IN DATABASE codeventra SET search_path = public;
ALTER ROLE cv_backup IN DATABASE codeventra SET default_transaction_read_only = on;
COMMIT;
