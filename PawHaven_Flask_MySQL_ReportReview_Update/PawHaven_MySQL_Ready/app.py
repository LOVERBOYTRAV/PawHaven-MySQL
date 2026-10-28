import os
from datetime import date
from functools import wraps

import mysql.connector
from mysql.connector import Error as MySQLError
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-development-secret")
MYSQL_DB = True

def get_db():
    """Create a MySQL connection from standard MYSQL* environment variables."""
    required = ["MYSQLHOST", "MYSQLUSER", "MYSQLPASSWORD", "MYSQLDATABASE"]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise RuntimeError("Missing MySQL environment variables: " + ", ".join(missing))
    return MySQLConnection()


class MySQLConnection:
    """Small adapter preserving the existing app's conn.execute(...).fetch*() style."""
    def __init__(self):
        self.raw = mysql.connector.connect(
            host=os.environ["MYSQLHOST"],
            port=int(os.environ.get("MYSQLPORT", "3306")),
            user=os.environ["MYSQLUSER"],
            password=os.environ["MYSQLPASSWORD"],
            database=os.environ["MYSQLDATABASE"],
            autocommit=False,
            connection_timeout=15,
            ssl_disabled=os.environ.get("MYSQL_SSL_DISABLED", "false").lower() == "true",
        )
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.raw.commit()
            else:
                self.raw.rollback()
        finally:
            self.raw.close()
        return False
    def execute(self, sql, params=None):
        cursor = self.raw.cursor(dictionary=True)
        cursor.execute(sql, params or ())
        return cursor
    def commit(self):
        self.raw.commit()


def init_db():
    """Create the application's tables on the configured MySQL database."""
    statements = [
        """CREATE TABLE IF NOT EXISTS admins (
            admin_id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS animals (
            animal_id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            species VARCHAR(30) NOT NULL,
            breed VARCHAR(100),
            sex VARCHAR(20) NOT NULL DEFAULT 'Unknown',
            estimated_age VARCHAR(60),
            rescue_date DATE,
            rescue_location VARCHAR(200),
            health_status VARCHAR(40) NOT NULL DEFAULT 'Needs assessment',
            description TEXT,
            image_url TEXT,
            adoption_status VARCHAR(30) NOT NULL DEFAULT 'Available',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_animals_status_created (adoption_status, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS adopters (
            adopter_id INT AUTO_INCREMENT PRIMARY KEY,
            full_name VARCHAR(120) NOT NULL,
            email VARCHAR(254) NOT NULL,
            phone VARCHAR(40) NOT NULL,
            address TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS adoption_applications (
            application_id INT AUTO_INCREMENT PRIMARY KEY,
            animal_id INT NOT NULL,
            adopter_id INT NOT NULL,
            reason TEXT NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'Pending',
            application_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_application_animal_adopter_status (animal_id, adopter_id, status),
            CONSTRAINT fk_app_animal FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE RESTRICT,
            CONSTRAINT fk_app_adopter FOREIGN KEY (adopter_id) REFERENCES adopters(adopter_id) ON DELETE RESTRICT,
            INDEX idx_app_status_date (status, application_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS rescue_reports (
            report_id INT AUTO_INCREMENT PRIMARY KEY,
            animal_id INT NULL,
            reporter_name VARCHAR(120) NOT NULL,
            reporter_contact VARCHAR(100) NOT NULL,
            location TEXT NOT NULL,
            description TEXT NOT NULL,
            image_url TEXT,
            status VARCHAR(30) NOT NULL DEFAULT 'New',
            report_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_report_animal FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE SET NULL,
            INDEX idx_report_date (report_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS medical_records (
            medical_id INT AUTO_INCREMENT PRIMARY KEY,
            animal_id INT NOT NULL,
            record_date DATE NOT NULL DEFAULT (CURRENT_DATE),
            diagnosis TEXT NOT NULL,
            treatment TEXT,
            vaccination_status VARCHAR(80) NOT NULL DEFAULT 'Unknown',
            notes TEXT,
            CONSTRAINT fk_medical_animal FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE CASCADE,
            INDEX idx_medical_animal_date (animal_id, record_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS animal_history (
            history_id INT AUTO_INCREMENT PRIMARY KEY,
            animal_id INT NULL,
            animal_name VARCHAR(100) NOT NULL,
            event_type VARCHAR(60) NOT NULL,
            details TEXT NOT NULL,
            event_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_history_animal FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE SET NULL,
            INDEX idx_history_event_date (event_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
    ]
    with get_db() as conn:
        for statement in statements:
            conn.execute(statement)


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            flash("Please sign in to access the admin dashboard.", "warning")
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    return {"current_year": date.today().year, "cloudinary_cloud_name": os.environ.get("CLOUDINARY_CLOUD_NAME", ""), "cloudinary_upload_preset": os.environ.get("CLOUDINARY_UPLOAD_PRESET", "")}


@app.route("/")
def index():
    with get_db() as conn:
        animals = conn.execute("""
            SELECT * FROM animals WHERE adoption_status = 'Available'
            ORDER BY created_at DESC LIMIT 6
        """).fetchall()
        stats = conn.execute("""
            SELECT SUM(adoption_status <> 'Adopted') AS in_care,
                   SUM(adoption_status = 'Available') AS available,
                   SUM(adoption_status = 'Adopted') AS adopted
            FROM animals
        """).fetchone()
    return render_template("index.html", animals=animals, stats=stats)


@app.route("/animals")
def animals():
    q = request.args.get("q", "").strip()[:100]
    species = request.args.get("species", "").strip()
    allowed_species = {"Dog", "Cat", "Other"}
    with get_db() as conn:
        sql = "SELECT * FROM animals WHERE adoption_status = 'Available'"
        params = []
        if species in allowed_species:
            sql += " AND species = %s"
            params.append(species)
        if q:
            sql += " AND (LOWER(name) LIKE LOWER(%s) OR LOWER(COALESCE(breed, '')) LIKE LOWER(%s) OR LOWER(COALESCE(rescue_location, '')) LIKE LOWER(%s))"
            params.extend([f"%{q}%"] * 3)
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql, params).fetchall()
    return render_template("animals.html", animals=rows, q=q, species=species)


@app.route("/animal/<int:animal_id>")
def animal_detail(animal_id):
    with get_db() as conn:
        animal = conn.execute("SELECT * FROM animals WHERE animal_id=%s", (animal_id,)).fetchone()
    if not animal:
        flash("That animal profile could not be found.", "warning")
        return redirect(url_for("animals"))
    return render_template("animal_detail.html", animal=animal)


@app.route("/adopt/<int:animal_id>", methods=["GET", "POST"])
def adopt(animal_id):
    with get_db() as conn:
        animal = conn.execute("SELECT * FROM animals WHERE animal_id=%s", (animal_id,)).fetchone()
    if not animal or animal["adoption_status"] != "Available":
        flash("This animal is not currently available for adoption.", "warning")
        return redirect(url_for("animals"))
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        reason = request.form.get("reason", "").strip()
        if not all([name, email, phone, address, reason]) or "@" not in email:
            flash("Please complete all fields with a valid email address.", "error")
            return render_template("adopt.html", animal=animal)
        if len(name) > 120 or len(email) > 254 or len(phone) > 40 or len(address) > 2000 or len(reason) > 3000:
            flash("One or more fields are too long. Please shorten your response.", "error")
            return render_template("adopt.html", animal=animal)
        with get_db() as conn:
            insert_cursor = conn.execute(
                "INSERT INTO adopters (full_name,email,phone,address) VALUES (%s,%s,%s,%s)",
                (name, email, phone, address)
            )
            adopter_id = insert_cursor.lastrowid
            insert_cursor.close()
            conn.execute(
                "INSERT INTO adoption_applications (animal_id,adopter_id,reason) VALUES (%s,%s,%s)",
                (animal_id, adopter_id, reason)
            )
            conn.execute("UPDATE animals SET adoption_status='Pending' WHERE animal_id=%s", (animal_id,))
        flash("Application received! Our team will review it and contact you.", "success")
        return redirect(url_for("animals"))
    return render_template("adopt.html", animal=animal)


@app.route("/report", methods=["GET", "POST"])
def report_rescue():
    if request.method == "POST":
        name = request.form.get("reporter_name", "").strip()
        contact = request.form.get("reporter_contact", "").strip()
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        image_url = request.form.get("image_url", "").strip()
        if not all([name, contact, location, description]):
            flash("Please complete every required field before submitting.", "error")
        elif max(map(len, [name, contact, location, description])) > 3000 or len(image_url) > 2000:
            flash("One or more fields are too long.", "error")
        elif image_url and not image_url.startswith("https://res.cloudinary.com/"):
            flash("Please upload the photo using the photo picker.", "error")
        else:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO rescue_reports (reporter_name,reporter_contact,location,description,image_url) VALUES (%s,%s,%s,%s,%s)",
                    (name, contact, location, description, image_url or None)
                )
            flash("Thank you for reporting an animal in need. The rescue team has received your report.", "success")
            return redirect(url_for("report_rescue"))
    return render_template("report.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_id"):
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with get_db() as conn:
            admin = conn.execute("SELECT * FROM admins WHERE username=%s", (username,)).fetchone()
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["admin_id"]
            session["admin_username"] = admin["username"]
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect username or password.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout", methods=["POST"])
@login_required
def admin_logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("index"))


@app.route("/admin")
@login_required
def admin_dashboard():
    with get_db() as conn:
        stats = conn.execute("""
            SELECT COUNT(*) AS total,
                   SUM(adoption_status='Available') AS available,
                   SUM(adoption_status='Pending') AS pending,
                   SUM(adoption_status='Adopted') AS adopted,
                   SUM(health_status='Under treatment') AS under_treatment,
                   SUM(adoption_status='Available') AS rescued_available
            FROM animals
        """).fetchone()
        applications = conn.execute("""
            SELECT aa.*, a.name AS animal_name, ad.full_name, ad.email, ad.phone
            FROM adoption_applications aa
            JOIN animals a ON a.animal_id=aa.animal_id
            JOIN adopters ad ON ad.adopter_id=aa.adopter_id
            ORDER BY aa.application_date DESC LIMIT 10
        """).fetchall()
        reports = conn.execute("SELECT * FROM rescue_reports ORDER BY report_date DESC LIMIT 8").fetchall()
        waiting_applicants = conn.execute("SELECT COUNT(*) AS total FROM adoption_applications WHERE status='Pending'").fetchone()["total"]
    return render_template("admin_dashboard.html", stats=stats, applications=applications, reports=reports, waiting_applicants=waiting_applicants)


@app.route("/admin/animals")
@login_required
def admin_animals():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM animals ORDER BY created_at DESC").fetchall()
    return render_template("admin_animals.html", animals=rows)


@app.route("/admin/animals/new", methods=["GET", "POST"])
@app.route("/admin/animals/<int:animal_id>/edit", methods=["GET", "POST"])
@login_required
def animal_form(animal_id=None):
    with get_db() as conn:
        animal = conn.execute("SELECT * FROM animals WHERE animal_id=%s", (animal_id,)).fetchone() if animal_id else None
    if animal_id and not animal:
        flash("Animal record not found.", "warning")
        return redirect(url_for("admin_animals"))
    if request.method == "POST":
        fields = {
            "name": request.form.get("name", "").strip(),
            "species": request.form.get("species", ""),
            "breed": request.form.get("breed", "").strip(),
            "sex": request.form.get("sex", "Unknown"),
            "estimated_age": request.form.get("estimated_age", "").strip(),
            "rescue_date": request.form.get("rescue_date") or None,
            "rescue_location": request.form.get("rescue_location", "").strip(),
            "health_status": request.form.get("health_status", "Needs assessment"),
            "description": request.form.get("description", "").strip(),
            "image_url": request.form.get("image_url", "").strip(),
            "adoption_status": request.form.get("adoption_status", "Available")
        }
        valid = (
            fields["name"] and len(fields["name"]) <= 100
            and fields["species"] in {"Dog", "Cat", "Other"}
            and fields["sex"] in {"Male", "Female", "Unknown"}
            and fields["health_status"] in {"Healthy", "Under treatment", "Needs assessment", "Recovered"}
            and fields["adoption_status"] in {"Available", "Pending", "Adopted", "Under care"}
            and all(len(str(fields[k] or "")) <= limit for k, limit in [
                ("breed",100),("estimated_age",60),("rescue_location",200),
                ("description",5000),("image_url",2000)])
        )
        if not valid:
            flash("Please check required fields and allowed values.", "error")
            return render_template("animal_form.html", animal=fields, editing=bool(animal_id))
        with get_db() as conn:
            if animal_id:
                conn.execute("""
                    UPDATE animals SET name=%s,species=%s,breed=%s,sex=%s,estimated_age=%s,
                    rescue_date=%s,rescue_location=%s,health_status=%s,description=%s,image_url=%s,
                    adoption_status=%s WHERE animal_id=%s
                """, (*fields.values(), animal_id))
            else:
                insert_cursor = conn.execute("""
                    INSERT INTO animals (name,species,breed,sex,estimated_age,rescue_date,rescue_location,
                    health_status,description,image_url,adoption_status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, tuple(fields.values()))
                new_animal_id = insert_cursor.lastrowid
                insert_cursor.close()
                conn.execute("INSERT INTO animal_history (animal_id,animal_name,event_type,details) VALUES (%s,%s,%s,%s)", (new_animal_id, fields["name"], "Rescue record created", "Initial rescue record added. Location: " + (fields["rescue_location"] or "Not recorded")))
        flash("Animal record saved successfully.", "success")
        return redirect(url_for("admin_animals"))
    return render_template("animal_form.html", animal=animal, editing=bool(animal_id))


@app.route("/admin/animals/<int:animal_id>/delete", methods=["POST"])
@login_required
def delete_animal(animal_id):
    with get_db() as conn:
        exists = conn.execute("SELECT animal_id FROM animals WHERE animal_id=%s", (animal_id,)).fetchone()
        if not exists:
            flash("Animal record not found.", "warning")
        else:
            linked = conn.execute("SELECT 1 FROM adoption_applications WHERE animal_id=%s LIMIT 1", (animal_id,)).fetchone()
            if linked:
                flash("This animal has application history and cannot be deleted. Change its status instead.", "warning")
            else:
                conn.execute("DELETE FROM animals WHERE animal_id=%s", (animal_id,))
                flash("Animal record deleted.", "success")
    return redirect(url_for("admin_animals"))


@app.route("/admin/applications/<int:application_id>/status", methods=["POST"])
@login_required
def update_application(application_id):
    status = request.form.get("status")
    if status not in {"Pending", "Approved", "Rejected", "Completed"}:
        flash("Invalid application status.", "error")
        return redirect(url_for("admin_dashboard"))
    with get_db() as conn:
        app_row = conn.execute("SELECT animal_id FROM adoption_applications WHERE application_id=%s", (application_id,)).fetchone()
        if not app_row:
            flash("Application not found.", "warning")
        else:
            conn.execute("UPDATE adoption_applications SET status=%s WHERE application_id=%s", (status, application_id))
            animal_name = conn.execute("SELECT name FROM animals WHERE animal_id=%s", (app_row["animal_id"],)).fetchone()
            if animal_name:
                conn.execute("INSERT INTO animal_history (animal_id,animal_name,event_type,details) VALUES (%s,%s,%s,%s)", (app_row["animal_id"], animal_name["name"], "Adoption application updated", "Application #" + str(application_id) + " status changed to " + status + "."))
            if status == "Completed":
                conn.execute("UPDATE animals SET adoption_status='Adopted' WHERE animal_id=%s", (app_row["animal_id"],))
            elif status == "Rejected":
                other_pending = conn.execute("""
                    SELECT 1 FROM adoption_applications
                    WHERE animal_id=%s AND status IN ('Pending','Approved') AND application_id<>%s LIMIT 1
                """, (app_row["animal_id"], application_id)).fetchone()
                if not other_pending:
                    conn.execute("UPDATE animals SET adoption_status='Available' WHERE animal_id=%s AND adoption_status='Pending'", (app_row["animal_id"],))
            elif status in {"Pending", "Approved"}:
                conn.execute("UPDATE animals SET adoption_status='Pending' WHERE animal_id=%s AND adoption_status<>'Adopted'", (app_row["animal_id"],))
            flash("Application status updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reports/<int:report_id>")
@login_required
def admin_report_detail(report_id):
    with get_db() as conn:
        report = conn.execute("SELECT * FROM rescue_reports WHERE report_id=%s", (report_id,)).fetchone()
        if not report:
            flash("Rescue report not found.", "warning")
            return redirect(url_for("admin_dashboard"))
        linked_animal = None
        if report.get("animal_id"):
            linked_animal = conn.execute("SELECT animal_id, name FROM animals WHERE animal_id=%s", (report["animal_id"],)).fetchone()
    return render_template("admin_report_detail.html", report=report, linked_animal=linked_animal)


@app.route("/admin/reports/<int:report_id>/approve", methods=["POST"])
@login_required
def approve_report(report_id):
    with get_db() as conn:
        report = conn.execute("SELECT * FROM rescue_reports WHERE report_id=%s", (report_id,)).fetchone()
        if not report:
            flash("Rescue report not found.", "warning")
            return redirect(url_for("admin_dashboard"))
        if report.get("animal_id"):
            flash("This report has already been linked to an animal record.", "info")
            return redirect(url_for("admin_report_detail", report_id=report_id))
        # Approval creates the animal record from the report, so admins do not need to re-enter it.
        animal_name = f"Reported stray #{report_id}"
        conn.execute("""
            INSERT INTO animals (name, species, sex, rescue_date, rescue_location,
                                 health_status, description, image_url, adoption_status)
            VALUES (%s, 'Unknown', 'Unknown', %s, %s, 'Needs assessment', %s, %s, 'Available')
        """, (animal_name, date.today().isoformat(), str(report["location"])[:200], report["description"], report.get("image_url")))
        created = conn.execute("SELECT LAST_INSERT_ID() AS animal_id").fetchone()
        animal_id = created["animal_id"]
        conn.execute("UPDATE rescue_reports SET animal_id=%s, status='In progress' WHERE report_id=%s", (animal_id, report_id))
        conn.execute("INSERT INTO animal_history (animal_id, animal_name, event_type, details) VALUES (%s,%s,%s,%s)", (animal_id, animal_name, "Rescue report approved", f"Created from public rescue report #{report_id}. Animal details should be reviewed by the rescue team."))
    flash("Report approved. An animal record was created automatically; review its details before listing it for adoption.", "success")
    return redirect(url_for("admin_report_detail", report_id=report_id))


@app.route("/admin/reports/<int:report_id>/status", methods=["POST"])
@login_required
def update_report(report_id):
    status = request.form.get("status")
    if status not in {"New", "In progress", "Resolved"}:
        flash("Invalid report status.", "error")
    else:
        with get_db() as conn:
            conn.execute("UPDATE rescue_reports SET status=%s WHERE report_id=%s", (status, report_id))
        flash("Rescue report updated.", "success")
    return redirect(url_for("admin_report_detail", report_id=report_id))


@app.route("/admin/animals/<int:animal_id>/medical", methods=["GET", "POST"])
@login_required
def animal_medical(animal_id):
    with get_db() as conn:
        animal = conn.execute("SELECT * FROM animals WHERE animal_id=%s", (animal_id,)).fetchone()
        if not animal:
            flash("Animal record not found.", "warning")
            return redirect(url_for("admin_animals"))
        if request.method == "POST":
            diagnosis = request.form.get("diagnosis", "").strip()[:3000]
            treatment = request.form.get("treatment", "").strip()[:3000]
            vaccination = request.form.get("vaccination_status", "Unknown")
            notes = request.form.get("notes", "").strip()[:3000]
            record_date = request.form.get("record_date") or date.today().isoformat()
            if not diagnosis or vaccination not in {"Unknown", "Not vaccinated", "Partially vaccinated", "Fully vaccinated"}:
                flash("Enter a diagnosis and choose a valid vaccination status.", "error")
            else:
                conn.execute("INSERT INTO medical_records (animal_id,record_date,diagnosis,treatment,vaccination_status,notes) VALUES (%s,%s,%s,%s,%s,%s)", (animal_id,record_date,diagnosis,treatment,vaccination,notes))
                conn.execute("INSERT INTO animal_history (animal_id,animal_name,event_type,details) VALUES (%s,%s,%s,%s)", (animal_id,animal["name"],"Medical update", diagnosis + (" — " + treatment if treatment else "")))
                status = request.form.get("health_status", animal["health_status"])
                if status in {"Healthy", "Under treatment", "Needs assessment", "Recovered"}:
                    conn.execute("UPDATE animals SET health_status=%s WHERE animal_id=%s", (status, animal_id))
                flash("Medical record saved.", "success")
                return redirect(url_for("animal_medical", animal_id=animal_id))
        records = conn.execute("SELECT * FROM medical_records WHERE animal_id=%s ORDER BY record_date DESC, medical_id DESC", (animal_id,)).fetchall()
    return render_template("animal_medical.html", animal=animal, records=records)


@app.route("/admin/matching", methods=["GET", "POST"])
@login_required
def animal_matching():
    species = request.values.get("species", "Any")
    age = request.values.get("age", "Any")
    size = request.values.get("size", "Any")
    valid_species = {"Any", "Dog", "Cat", "Other"}
    valid_age = {"Any", "Young", "Adult", "Senior"}
    valid_size = {"Any", "Small", "Medium", "Large"}
    if species not in valid_species: species = "Any"
    if age not in valid_age: age = "Any"
    if size not in valid_size: size = "Any"
    clauses = ["adoption_status='Available'"]
    params = []
    if species != "Any": clauses.append("species=%s"); params.append(species)
    if age != "Any":
        age_terms = {"Young": ["%puppy%", "%kitten%", "%month%"], "Adult": ["%adult%", "%year%"], "Senior": ["%senior%", "%old%"]}[age]
        clauses.append("(" + " OR ".join(["LOWER(COALESCE(estimated_age, ' ') ) LIKE %s"] * len(age_terms)) + ")")
        params.extend(age_terms)
    # Size is not a stored field; match description/breed hints only and explain that it is approximate.
    if size != "Any":
        terms = {"Small": ["%small%", "%toy%"], "Medium": ["%medium%"], "Large": ["%large%", "%giant%"]}[size]
        clauses.append("(" + " OR ".join(["LOWER(CONCAT(COALESCE(description,''), ' ', COALESCE(breed,''))) LIKE %s"] * len(terms)) + ")")
        params.extend(terms)
    with get_db() as conn:
        matches = conn.execute("SELECT * FROM animals WHERE " + " AND ".join(clauses) + " ORDER BY created_at DESC", params).fetchall()
    return render_template("animal_matching.html", animals=matches, species=species, age=age, size=size)


@app.route("/admin/history")
@login_required
def animal_history():
    with get_db() as conn:
        history = conn.execute("SELECT * FROM animal_history ORDER BY event_date DESC LIMIT 300").fetchall()
    return render_template("animal_history.html", history=history)


@app.cli.command("create-admin")
def create_admin():
    """Create an admin using ADMIN_USERNAME and ADMIN_PASSWORD environment variables."""
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not username or len(password) < 12:
        raise SystemExit("Set ADMIN_USERNAME and ADMIN_PASSWORD (at least 12 characters) before running this command.")
    with get_db() as conn:
        existing = conn.execute("SELECT admin_id FROM admins WHERE username=%s", (username,)).fetchone()
        if existing:
            conn.execute("UPDATE admins SET password_hash=%s WHERE username=%s", (generate_password_hash(password), username))
            print("Admin password updated.")
        else:
            conn.execute("INSERT INTO admins (username,password_hash) VALUES (%s,%s)", (username, generate_password_hash(password)))
            print("Admin account created.")


@app.cli.command("init-db")
def init_db_command():
    init_db()
    print("Database tables are ready.")


@app.route("/health")
def health():
    try:
        with get_db() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "database": "connected"}, 200
    except Exception:
        return {"status": "error", "database": "unavailable"}, 503


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
