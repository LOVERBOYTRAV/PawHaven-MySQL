# PawHaven — MySQL migration and Render deployment

This package converts the Flask app from PostgreSQL/psycopg to MySQL Connector/Python and keeps the existing pages/routes/templates and Cloudinary environment configuration. It also includes a guarded one-time migration script for copying the existing PostgreSQL rows into a newly created, empty MySQL database.

## Important: protect the existing records
- Do not delete the Render PostgreSQL database yet. It remains the source of truth until data is copied and verified.
- The new app creates the same seven application tables: `admins`, `animals`, `adopters`, `adoption_applications`, `rescue_reports`, `medical_records`, and `animal_history`.
- The earlier assumption of six tables was incomplete for this codebase: the app itself creates seven tables.
- `schema_mysql.sql` is for a new MySQL database. It creates tables but does not copy PostgreSQL records.
- MySQL Workbench is the client; Render cannot connect to a MySQL server running only on your own PC. Use a hosted MySQL provider that supports external TLS connections and keep credentials in Render environment variables.

## MySQL provider values
Create a hosted MySQL 8 database, then set these environment variables in the Render web service using values from the provider dashboard:
- `MYSQLHOST`: database host (not `localhost`)
- `MYSQLPORT`: provider's port, often `3306`
- `MYSQLDATABASE`: database name
- `MYSQLUSER`: database username
- `MYSQLPASSWORD`: database password
- `MYSQL_SSL_DISABLED`: leave unset/false for TLS; only set true for a trusted local development server that does not support TLS
- `SECRET_KEY`: long random secret
- `ADMIN_USERNAME` and `ADMIN_PASSWORD`: admin login values (password must be at least 12 characters)
- `CLOUDINARY_CLOUD_NAME` and `CLOUDINARY_UPLOAD_PRESET`: keep the existing values if using Cloudinary uploads

## Deploy sequence
1. Create the hosted MySQL database and a backup of the current PostgreSQL database.
2. Inspect source PostgreSQL tables/columns and row counts. Do not assume all records have already been copied.
3. Create the schema by running `schema_mysql.sql` in MySQL Workbench or `flask --app app init-db` against the target database. Install `requirements-migration.txt`, set `SOURCE_POSTGRES_URL` plus the `MYSQL*` environment variables, and run `python migrate_postgres_to_mysql.py`. It preserves primary keys, copies the seven tables in foreign-key order, refuses non-empty target tables, and checks row counts. Use a brand-new empty target database for the first run.
4. Deploy this package to a separate branch or staging Render service first, and configure the MySQL environment variables there.
5. Verify `/health`, public pages, animal search, rescue report submission, admin login, medical records, and adoption flow.
6. Only after verification, point production at MySQL. Keep PostgreSQL unchanged as a rollback backup until the project is accepted.

## Local use
Install dependencies with `python -m pip install -r requirements.txt`. Configure the same `MYSQL*` environment variables in your local shell. You can use `schema_mysql.sql` in MySQL Workbench to create the tables.
