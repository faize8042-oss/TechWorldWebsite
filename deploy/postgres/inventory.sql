-- READ ONLY inventory; operator must choose/verify target privately before use.
-- No SQL in this repository was executed during C6.2.1 implementation.
BEGIN READ ONLY;
SELECT current_database(), session_user, current_user, version();
SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolcanlogin, rolinherit,
       rolreplication, rolbypassrls FROM pg_roles;
SELECT roleid::regrole, member::regrole, admin_option, inherit_option, set_option FROM pg_auth_members;
SELECT datname, datdba::regrole, datacl FROM pg_database;
SELECT nspname, nspowner::regrole, nspacl FROM pg_namespace;
SELECT n.nspname, c.relname, c.relkind, c.relowner::regrole, c.relacl, c.relrowsecurity
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public';
SELECT n.nspname, p.proname, p.prokind, pg_get_function_identity_arguments(p.oid) AS identity_arguments, p.proowner::regrole, p.proacl, p.prosecdef
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public';
SELECT n.nspname, t.typname, t.typtype, t.typelem, t.typrelid,
       c.relkind, t.typowner::regrole, t.typacl,
       CASE WHEN t.typtype='c' AND c.relkind='c' THEN 'standalone composite'
            WHEN t.typtype='c' THEN 'relation row type'
            WHEN t.typelem<>0 THEN 'generated array or element-bearing type'
            ELSE 'independent type' END AS type_class
FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
LEFT JOIN pg_class c ON c.oid=t.typrelid WHERE n.nspname='public';
SELECT defaclrole::regrole, defaclnamespace::regnamespace, defaclobjtype, defaclacl FROM pg_default_acl;
SELECT extname, extowner::regrole, extnamespace::regnamespace FROM pg_extension;
SELECT * FROM pg_policies;
COMMIT;
