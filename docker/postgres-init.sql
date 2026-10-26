-- Development-only credentials. Production roles are provisioned separately.
CREATE ROLE social_app LOGIN PASSWORD 'social_app_local' NOSUPERUSER NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE social TO social_app;
GRANT USAGE ON SCHEMA public TO social_app;
ALTER DEFAULT PRIVILEGES FOR ROLE social_admin IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO social_app;
ALTER DEFAULT PRIVILEGES FOR ROLE social_admin IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO social_app;
