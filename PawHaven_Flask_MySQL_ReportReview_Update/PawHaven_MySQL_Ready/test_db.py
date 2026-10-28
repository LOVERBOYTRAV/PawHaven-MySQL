import os
import mysql.connector

required = ["MYSQLHOST", "MYSQLUSER", "MYSQLPASSWORD", "MYSQLDATABASE"]
missing = [key for key in required if not os.environ.get(key)]
if missing:
    raise SystemExit("Set these environment variables first: " + ", ".join(missing))

conn = mysql.connector.connect(
    host=os.environ["MYSQLHOST"],
    port=int(os.environ.get("MYSQLPORT", "3306")),
    user=os.environ["MYSQLUSER"],
    password=os.environ["MYSQLPASSWORD"],
    database=os.environ["MYSQLDATABASE"],
    connection_timeout=15,
    ssl_disabled=os.environ.get("MYSQL_SSL_DISABLED", "false").lower() == "true",
)
try:
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    print("Connected to PawHaven MySQL successfully!")
    for (table_name,) in cur.fetchall():
        print("-", table_name)
    cur.close()
finally:
    conn.close()
