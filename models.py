from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

db = SQLAlchemy()

STATUSES = ["Open", "In Progress", "On Hold", "Resolved", "Closed"]
PRIORITIES = ["Low", "Medium", "High", "Urgent"]


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=True)
    tracking_token = db.Column(db.String(64), unique=True, nullable=False)

    tickets = db.relationship("Ticket", backref="customer", cascade="all, delete-orphan")


class CustomFieldDefinition(db.Model):
    __tablename__ = "custom_field_definitions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    field_type = db.Column(db.String(20), default="text")  # text, number, date, textarea


class Ticket(db.Model):
    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    updated_date = db.Column(db.DateTime, default=datetime.utcnow)
    updated_notes = db.Column(db.Text, default="")
    custom_data = db.Column(db.Text, default="{}")  # JSON blob of custom field values
    status = db.Column(db.String(30), default="Open")
    priority = db.Column(db.String(30), default="Medium")


def migrate_schema():
    """Add new columns to an existing SQLite DB without losing data."""
    cols = {row[1] for row in db.session.execute(text("PRAGMA table_info(tickets)"))}
    if "status" not in cols:
        db.session.execute(text("ALTER TABLE tickets ADD COLUMN status VARCHAR(30) DEFAULT 'Open'"))
    if "priority" not in cols:
        db.session.execute(text("ALTER TABLE tickets ADD COLUMN priority VARCHAR(30) DEFAULT 'Medium'"))
    db.session.commit()
