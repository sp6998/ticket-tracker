"""
Customer Ticket Tracker
-----------------------
  - Core fields: ticket id, customer name, created date, updated notes (+ status, priority)
  - Admin-defined custom fields (no code changes needed)
  - Per-customer export in CSV, Excel and PDF
  - Unique read-only tracking URL per customer
"""

import json
import os
import uuid
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, Response, abort
from sqlalchemy import or_

from exporters import build_rows, to_csv, to_excel, to_pdf
from models import db, Customer, Ticket, CustomFieldDefinition, STATUSES, PRIORITIES, migrate_schema

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///tickets.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
# Public base URL used in shared tracking links, e.g. https://track.example.com
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")


@app.template_global()
def public_track_url(token):
    """Shareable tracking URL; uses PUBLIC_BASE_URL when set."""
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL + url_for("track", token=token)
    return url_for("track", token=token, _external=True)

db.init_app(app)

with app.app_context():
    db.create_all()
    migrate_schema()


@app.context_processor
def inject_globals():
    return {"STATUSES": STATUSES, "PRIORITIES": PRIORITIES, "now": datetime.utcnow()}


def get_custom_field_defs():
    return CustomFieldDefinition.query.order_by(CustomFieldDefinition.id).all()


def parse_custom_fields_from_form(form):
    return {f.name: form.get(f"custom_{f.id}", "") for f in get_custom_field_defs()}


# ---------------------------------------------------------------------------
# Dashboard / Ticket list
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    customer_filter = request.args.get("customer_id", type=int)
    status_filter = request.args.get("status", "")
    q = request.args.get("q", "").strip()

    query = Ticket.query.join(Customer)
    if customer_filter:
        query = query.filter(Ticket.customer_id == customer_filter)
    if status_filter:
        query = query.filter(Ticket.status == status_filter)
    if q:
        like = f"%{q}%"
        conds = [Customer.name.ilike(like), Ticket.updated_notes.ilike(like), Ticket.custom_data.ilike(like)]
        if q.lstrip("#").isdigit():
            conds.append(Ticket.id == int(q.lstrip("#")))
        query = query.filter(or_(*conds))
    tickets = query.order_by(Ticket.created_date.desc()).all()

    all_tickets = Ticket.query.all()
    stats = {
        "total": len(all_tickets),
        "open": sum(1 for t in all_tickets if (t.status or "Open") in ("Open", "In Progress", "On Hold")),
        "resolved": sum(1 for t in all_tickets if t.status in ("Resolved", "Closed")),
        "customers": Customer.query.count(),
    }
    return render_template(
        "index.html",
        tickets=tickets,
        customers=Customer.query.order_by(Customer.name).all(),
        selected_customer=customer_filter,
        selected_status=status_filter,
        q=q,
        stats=stats,
    )


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

@app.route("/customers", methods=["GET", "POST"])
def customers():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        if not name:
            flash("Customer name is required.", "error")
        else:
            db.session.add(Customer(name=name, email=email, tracking_token=uuid.uuid4().hex))
            db.session.commit()
            flash(f"Customer '{name}' created.", "success")
        return redirect(url_for("customers"))

    return render_template("customers.html", customers=Customer.query.order_by(Customer.name).all())


@app.route("/customers/<int:customer_id>/delete", methods=["POST"])
def delete_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    db.session.delete(customer)
    db.session.commit()
    flash("Customer deleted.", "success")
    return redirect(url_for("customers"))


@app.route("/customers/<int:customer_id>/regenerate", methods=["POST"])
def regenerate_token(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    customer.tracking_token = uuid.uuid4().hex
    db.session.commit()
    flash(f"New tracking link generated for '{customer.name}'. The old link no longer works.", "success")
    return redirect(url_for("customers"))


# ---------------------------------------------------------------------------
# Custom fields
# ---------------------------------------------------------------------------

@app.route("/fields", methods=["GET", "POST"])
def fields():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        field_type = request.form.get("field_type", "text")
        if not name:
            flash("Field name is required.", "error")
        elif CustomFieldDefinition.query.filter_by(name=name).first():
            flash("A field with this name already exists.", "error")
        else:
            db.session.add(CustomFieldDefinition(name=name, field_type=field_type))
            db.session.commit()
            flash(f"Custom field '{name}' added.", "success")
        return redirect(url_for("fields"))

    return render_template("fields.html", fields=get_custom_field_defs())


@app.route("/fields/<int:field_id>/delete", methods=["POST"])
def delete_field(field_id):
    field = CustomFieldDefinition.query.get_or_404(field_id)
    db.session.delete(field)
    db.session.commit()
    flash("Custom field removed.", "success")
    return redirect(url_for("fields"))


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

def _clean_choice(value, choices, default):
    return value if value in choices else default


@app.route("/tickets/new", methods=["GET", "POST"])
def new_ticket():
    if request.method == "POST":
        customer_id = request.form.get("customer_id", type=int)
        if not customer_id:
            flash("Please select a customer.", "error")
            return redirect(url_for("new_ticket"))
        now = datetime.utcnow()
        ticket = Ticket(
            customer_id=customer_id,
            created_date=now,
            updated_date=now,
            updated_notes=request.form.get("notes", "").strip(),
            status=_clean_choice(request.form.get("status"), STATUSES, "Open"),
            priority=_clean_choice(request.form.get("priority"), PRIORITIES, "Medium"),
            custom_data=json.dumps(parse_custom_fields_from_form(request.form)),
        )
        db.session.add(ticket)
        db.session.commit()
        flash(f"Ticket #{ticket.id} created.", "success")
        return redirect(url_for("index"))

    return render_template(
        "ticket_form.html",
        customers=Customer.query.order_by(Customer.name).all(),
        custom_fields=get_custom_field_defs(),
        ticket=None,
        existing_custom={},
        preselect=request.args.get("customer_id", type=int),
    )


@app.route("/tickets/<int:ticket_id>/edit", methods=["GET", "POST"])
def edit_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    if request.method == "POST":
        ticket.customer_id = request.form.get("customer_id", type=int) or ticket.customer_id
        ticket.updated_notes = request.form.get("notes", "").strip()
        ticket.status = _clean_choice(request.form.get("status"), STATUSES, ticket.status)
        ticket.priority = _clean_choice(request.form.get("priority"), PRIORITIES, ticket.priority)
        ticket.custom_data = json.dumps(parse_custom_fields_from_form(request.form))
        ticket.updated_date = datetime.utcnow()
        db.session.commit()
        flash(f"Ticket #{ticket.id} updated.", "success")
        return redirect(url_for("index"))

    return render_template(
        "ticket_form.html",
        customers=Customer.query.order_by(Customer.name).all(),
        custom_fields=get_custom_field_defs(),
        ticket=ticket,
        existing_custom=json.loads(ticket.custom_data or "{}"),
        preselect=None,
    )


@app.route("/tickets/<int:ticket_id>/delete", methods=["POST"])
def delete_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    db.session.delete(ticket)
    db.session.commit()
    flash(f"Ticket #{ticket_id} deleted.", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Export (CSV / Excel / PDF)
# ---------------------------------------------------------------------------

EXPORT_FORMATS = {
    "csv": ("text/csv; charset=utf-8", "csv"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
    "pdf": ("application/pdf", "pdf"),
}


@app.route("/export/<int:customer_id>")
@app.route("/export/<int:customer_id>/<fmt>")
def export_customer_tickets(customer_id, fmt="csv"):
    if fmt not in EXPORT_FORMATS:
        abort(400)
    customer = Customer.query.get_or_404(customer_id)
    tickets = Ticket.query.filter_by(customer_id=customer_id).order_by(Ticket.created_date).all()
    header, rows = build_rows(customer, tickets, get_custom_field_defs())

    if fmt == "csv":
        payload = to_csv(header, rows)
    elif fmt == "xlsx":
        payload = to_excel(header, rows, customer.name)
    else:
        payload = to_pdf(header, rows, customer.name)

    mimetype, ext = EXPORT_FORMATS[fmt]
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in customer.name)
    return Response(payload, mimetype=mimetype,
                    headers={"Content-Disposition": f"attachment; filename={safe}_tickets.{ext}"})


# ---------------------------------------------------------------------------
# Customer-facing tracking page
# ---------------------------------------------------------------------------

@app.route("/track/<token>")
def track(token):
    customer = Customer.query.filter_by(tracking_token=token).first()
    if not customer:
        abort(404)
    tickets = Ticket.query.filter_by(customer_id=customer.id).order_by(Ticket.created_date.desc()).all()
    tickets_data = [{"ticket": t, "custom": json.loads(t.custom_data or "{}")} for t in tickets]
    return render_template("track.html", customer=customer, tickets_data=tickets_data,
                           custom_fields=get_custom_field_defs())


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
