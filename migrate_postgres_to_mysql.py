"""One-time, row-preserving migration from the existing PawHaven PostgreSQL DB to MySQL.

Run only after backing up both databases and creating the MySQL schema. The script
refuses to run if any destination application table already contains rows.
"""
import os
import sys
import psycopg
import mysql.connector

SOURCE_URL = os.environ.get("SOURCE_POSTGRES_URL")
required = ["MYSQLHOST", "MYSQLUSER", "MYSQLPASSWORD", "MYSQLDATABASE"]
missing = [name for name in required if not os.environ.get(name)]
if not SOURCE_URL:
    missing.append("SOURCE_POSTGRES_URL")
if missing:
    raise SystemExit("Missing environment variables: " + ", ".join(missing))

TABLES = ["admins", "animals", "adopters", "adoption_applications", "rescue_reports", "medical_records", "animal_history"]

def main():
    print("Connecting to source PostgreSQL and destination MySQL...")
    with psycopg.connect(SOURCE_URL, connect_timeout=15) as pg:
        my = mysql.connector.connect(
            host=os.environ["MYSQLHOST"],
            port=int(os.environ.get("MYSQLPORT", "3306")),
            user=os.environ["MYSQLUSER"],
            password=os.environ["MYSQLPASSWORD"],
            database=os.environ["MYSQLDATABASE"],
            connection_timeout=15,
            ssl_disabled=os.environ.get("MYSQL_SSL_DISABLED", "false").lower() == "true",
            autocommit=False,
        )
        try:
            mc = my.cursor()
            # Verify source tables and target emptiness before copying any records.
            with pg.cursor() as pc:
                pc.execute("""SELECT table_name FROM information_schema.tables
                               WHERE table_schema='public' AND table_type='BASE TABLE'""")
                source_tables = {row[0] for row in pc.fetchall()}
            missing_tables = [t for t in TABLES if t not in source_tables]
            if missing_tables:
                raise RuntimeError("Expected source tables missing: " + ", ".join(missing_tables))
            for table in TABLES:
                mc.execute(f"SELECT COUNT(*) FROM `{table}`")
                count = mc.fetchone()[0]
                if count:
                    raise RuntimeError(f"Destination table `{table}` already has {count} rows. No data was copied. Use an empty target database to avoid duplicates/overwrites.")

            source_counts = {}
            for table in TABLES:
                with pg.cursor() as pc:
                    pc.execute(f'SELECT * FROM public."{table}"')
                    columns = [d.name for d in pc.description]
                    rows = pc.fetchall()
                source_counts[table] = len(rows)
                if rows:
                    col_sql = ", ".join(f"`{c}`" for c in columns)
                    placeholders = ", ".join(["%s"] * len(columns))
                    insert_sql = f"INSERT INTO `{table}` ({col_sql}) VALUES ({placeholders})"
                    mc.executemany(insert_sql, [tuple(row) for row in rows])
                print(f"Copied {table}: {len(rows)} rows")
            my.commit()

            print("\n=== VERIFIED ROW COUNTS ===")
            failed = False
            for table in TABLES:
                mc.execute(f"SELECT COUNT(*) FROM `{table}`")
                destination_count = mc.fetchone()[0]
                source_count = source_counts[table]
                status = "OK" if source_count == destination_count else "MISMATCH"
                print(f"{table}: PostgreSQL={source_count}, MySQL={destination_count} [{status}]")
                failed = failed or source_count != destination_count
            if failed:
                raise RuntimeError("One or more row counts do not match. Keep PostgreSQL unchanged and investigate before switching the website.")
            print("\nMigration and row-count verification completed. Keep the PostgreSQL database as a backup until the deployed MySQL app is fully tested.")
        except Exception:
            my.rollback()
            raise
        finally:
            my.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Migration stopped:", exc, file=sys.stderr)
        sys.exit(1)
