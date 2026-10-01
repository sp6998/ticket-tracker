# Customer Ticket Tracker

A simple Flask + SQLite web app to manage customer support tickets.

## Features
- Core fields: Ticket ID, Customer Name, Created Date, Updated Notes
- **Custom fields**: add/remove fields from the UI (`/fields`) — no code changes or redeploys needed
- **CSV export** of all tickets for a specific customer (`/export/<customer_id>`), includes custom fields as columns
- **Per-customer tracking URL**: each customer gets a unique link (`/track/<token>`) to view their own tickets only, read-only, no login required

## Setup
```bash
cd ticket-tracker
pip install -r requirements.txt
python3 app.py
```
App runs at `http://localhost:5000`.

## Usage
1. Go to **Customers** → add a customer. A unique tracking URL is generated automatically.
2. Go to **Custom Fields** → define any extra fields you need (e.g. Priority, Product Area). They appear instantly on the ticket form.
3. Go to **Tickets** → create/edit tickets, filter by customer, export CSV.
4. Share the customer's tracking URL (shown on the Customers page) with them — they can bookmark it to check ticket status anytime.

## Notes / Next steps for production
- Set `app.secret_key` from an environment variable.
- Switch `SQLALCHEMY_DATABASE_URI` to Postgres/MySQL for multi-user concurrent access.
- Add admin authentication (e.g. Flask-Login) before exposing the admin routes publicly.
- Consider rate-limiting or expiring tracking tokens if stronger security is needed.

## Exports
Each customer's tickets can be exported from the Customers page (or the Tickets page with a customer filter):
- CSV: `/export/<customer_id>/csv`
- Excel: `/export/<customer_id>/xlsx`
- PDF: `/export/<customer_id>/pdf`
