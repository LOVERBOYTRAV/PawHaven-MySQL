-- PawHaven MySQL schema for MySQL 8.0+
-- Safe to run repeatedly: CREATE TABLE IF NOT EXISTS does not delete existing data.
-- Run this in MySQL Workbench after creating an empty database named pawhaven_db.
CREATE DATABASE IF NOT EXISTS pawhaven_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE pawhaven_db;

CREATE TABLE IF NOT EXISTS admins (
 admin_id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(80) UNIQUE NOT NULL,
 password_hash TEXT NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS animals (
 animal_id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL,
 species VARCHAR(30) NOT NULL, breed VARCHAR(100), sex VARCHAR(20) NOT NULL DEFAULT 'Unknown',
 estimated_age VARCHAR(60), rescue_date DATE, rescue_location VARCHAR(200),
 health_status VARCHAR(40) NOT NULL DEFAULT 'Needs assessment', description TEXT, image_url TEXT,
 adoption_status VARCHAR(30) NOT NULL DEFAULT 'Available', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 INDEX idx_animals_status_created (adoption_status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS adopters (
 adopter_id INT AUTO_INCREMENT PRIMARY KEY, full_name VARCHAR(120) NOT NULL,
 email VARCHAR(254) NOT NULL, phone VARCHAR(40) NOT NULL, address TEXT NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS adoption_applications (
 application_id INT AUTO_INCREMENT PRIMARY KEY, animal_id INT NOT NULL, adopter_id INT NOT NULL,
 reason TEXT NOT NULL, status VARCHAR(30) NOT NULL DEFAULT 'Pending',
 application_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY uq_application_animal_adopter_status (animal_id, adopter_id, status),
 CONSTRAINT fk_app_animal FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE RESTRICT,
 CONSTRAINT fk_app_adopter FOREIGN KEY (adopter_id) REFERENCES adopters(adopter_id) ON DELETE RESTRICT,
 INDEX idx_app_status_date (status, application_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS rescue_reports (
 report_id INT AUTO_INCREMENT PRIMARY KEY, animal_id INT NULL, reporter_name VARCHAR(120) NOT NULL,
 reporter_contact VARCHAR(100) NOT NULL, location TEXT NOT NULL, description TEXT NOT NULL, image_url TEXT,
 status VARCHAR(30) NOT NULL DEFAULT 'New', report_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_report_animal FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE SET NULL,
 INDEX idx_report_date (report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS medical_records (
 medical_id INT AUTO_INCREMENT PRIMARY KEY, animal_id INT NOT NULL,
 record_date DATE NOT NULL DEFAULT (CURRENT_DATE), diagnosis TEXT NOT NULL, treatment TEXT,
 vaccination_status VARCHAR(80) NOT NULL DEFAULT 'Unknown', notes TEXT,
 CONSTRAINT fk_medical_animal FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE CASCADE,
 INDEX idx_medical_animal_date (animal_id, record_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS animal_history (
 history_id INT AUTO_INCREMENT PRIMARY KEY, animal_id INT NULL, animal_name VARCHAR(100) NOT NULL,
 event_type VARCHAR(60) NOT NULL, details TEXT NOT NULL,
 event_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_history_animal FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE SET NULL,
 INDEX idx_history_event_date (event_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
