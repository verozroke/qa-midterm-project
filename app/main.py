"""Ticket management system — Flask application with SQLite."""

from __future__ import annotations

import os
import uuid
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template, redirect,
    url_for, session, flash, g,
)

# ---------------------------------------------------------------------------
# Database helpers (plain sqlite3 — no ORM, keeps it simple)
# ---------------------------------------------------------------------------
import sqlite3

DATABASE = os.getenv("DATABASE_PATH", "tickets.db")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app: Flask):
    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tickets (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'medium',
                status TEXT NOT NULL DEFAULT 'open',
                category TEXT NOT NULL DEFAULT 'general',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (created_by) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        # Seed default user
        pw_hash = hashlib.sha256("ChangeMe123!".encode()).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT OR IGNORE INTO users (id, username, password_hash, email, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("user-001", "test.user", pw_hash, "test@example.com", now),
        )
        db.commit()
        close_db()


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------
TOKENS: dict[str, dict] = {}  # token -> {user_id, expires_at}


def _hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def _create_token(user_id: str) -> str:
    token = secrets.token_hex(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=2)
    TOKENS[token] = {"user_id": user_id, "expires_at": expires}
    return token


def _validate_token(token: str | None) -> str | None:
    if not token:
        return None
    token = token.replace("Bearer ", "").strip()
    info = TOKENS.get(token)
    if not info:
        return None
    if datetime.now(timezone.utc) > info["expires_at"]:
        del TOKENS[token]
        return None
    return info["user_id"]


def api_auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        user_id = _validate_token(auth)
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
        g.current_user_id = user_id
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
    app.teardown_appcontext(close_db)

    # ── API: Auth ─────────────────────────────────────────────────────
    @app.route("/api/auth/login", methods=["POST"])
    def api_login():
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400
        username = data.get("username", "").strip()
        password = data.get("password", "")
        if not username or not password:
            return jsonify({"error": "Username and password required"}), 400

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not user or user["password_hash"] != _hash_pw(password):
            return jsonify({"error": "Invalid credentials"}), 401

        token = _create_token(user["id"])
        # Create notification
        db.execute(
            "INSERT INTO notifications (id, user_id, message, created_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4())[:8], user["id"], "Login successful", datetime.now(timezone.utc).isoformat()),
        )
        db.commit()
        return jsonify({"token": token, "user_id": user["id"], "username": user["username"]}), 200

    @app.route("/api/auth/logout", methods=["POST"])
    @api_auth_required
    def api_logout():
        auth = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        TOKENS.pop(auth, None)
        return jsonify({"message": "Logged out"}), 200

    # ── API: Tickets ──────────────────────────────────────────────────
    @app.route("/api/tickets", methods=["GET"])
    @api_auth_required
    def api_list_tickets():
        db = get_db()
        rows = db.execute(
            "SELECT * FROM tickets WHERE created_by = ? ORDER BY created_at DESC",
            (g.current_user_id,),
        ).fetchall()
        return jsonify([dict(r) for r in rows]), 200

    @app.route("/api/tickets", methods=["POST"])
    @api_auth_required
    def api_create_ticket():
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400
        errors = {}
        title = (data.get("title") or "").strip()
        description = (data.get("description") or "").strip()
        priority = (data.get("priority") or "medium").strip().lower()
        category = (data.get("category") or "general").strip().lower()
        if not title:
            errors["title"] = "Title is required"
        elif len(title) > 200:
            errors["title"] = "Title must be 200 characters or fewer"
        if not description:
            errors["description"] = "Description is required"
        if priority not in ("low", "medium", "high", "critical"):
            errors["priority"] = "Priority must be low, medium, high, or critical"
        if errors:
            return jsonify({"errors": errors}), 422

        now = datetime.now(timezone.utc).isoformat()
        ticket_id = str(uuid.uuid4())[:8]
        db = get_db()
        db.execute(
            "INSERT INTO tickets (id, title, description, priority, status, category, created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?)",
            (ticket_id, title, description, priority, category, g.current_user_id, now, now),
        )
        # Notification
        db.execute(
            "INSERT INTO notifications (id, user_id, message, created_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4())[:8], g.current_user_id, f"Ticket '{title}' created", now),
        )
        db.commit()
        ticket = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return jsonify(dict(ticket)), 201

    @app.route("/api/tickets/<ticket_id>", methods=["GET"])
    @api_auth_required
    def api_get_ticket(ticket_id):
        db = get_db()
        ticket = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if not ticket:
            return jsonify({"error": "Ticket not found"}), 404
        return jsonify(dict(ticket)), 200

    @app.route("/api/tickets/<ticket_id>", methods=["PUT"])
    @api_auth_required
    def api_update_ticket(ticket_id):
        db = get_db()
        ticket = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if not ticket:
            return jsonify({"error": "Ticket not found"}), 404
        data = request.get_json(silent=True) or {}
        title = data.get("title", ticket["title"])
        description = data.get("description", ticket["description"])
        priority = data.get("priority", ticket["priority"])
        status = data.get("status", ticket["status"])
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "UPDATE tickets SET title=?, description=?, priority=?, status=?, updated_at=? WHERE id=?",
            (title, description, priority, status, now, ticket_id),
        )
        db.commit()
        updated = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return jsonify(dict(updated)), 200

    @app.route("/api/tickets/<ticket_id>", methods=["DELETE"])
    @api_auth_required
    def api_delete_ticket(ticket_id):
        db = get_db()
        ticket = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if not ticket:
            return jsonify({"error": "Ticket not found"}), 404
        db.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
        db.commit()
        return jsonify({"message": "Ticket deleted"}), 200

    # ── API: Notifications ────────────────────────────────────────────
    @app.route("/api/notifications", methods=["GET"])
    @api_auth_required
    def api_get_notifications():
        db = get_db()
        rows = db.execute(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 20",
            (g.current_user_id,),
        ).fetchall()
        return jsonify([dict(r) for r in rows]), 200

    @app.route("/api/notifications/<notif_id>/read", methods=["PUT"])
    @api_auth_required
    def api_mark_notification_read(notif_id):
        db = get_db()
        db.execute("UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?", (notif_id, g.current_user_id))
        db.commit()
        return jsonify({"message": "Notification marked as read"}), 200

    # ── UI Routes ─────────────────────────────────────────────────────
    @app.route("/")
    def index():
        return redirect(url_for("login_page"))

    @app.route("/login", methods=["GET", "POST"])
    def login_page():
        if request.method == "GET":
            return render_template("login.html", error=None)
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not user or user["password_hash"] != _hash_pw(password):
            return render_template("login.html", error="Invalid username or password")
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return redirect(url_for("dashboard_page"))

    @app.route("/dashboard")
    def dashboard_page():
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        db = get_db()
        tickets = db.execute(
            "SELECT * FROM tickets WHERE created_by = ? ORDER BY created_at DESC",
            (session["user_id"],),
        ).fetchall()
        notifications = db.execute(
            "SELECT * FROM notifications WHERE user_id = ? AND is_read = 0 ORDER BY created_at DESC LIMIT 5",
            (session["user_id"],),
        ).fetchall()
        return render_template("dashboard.html", tickets=tickets, notifications=notifications, username=session.get("username"))

    @app.route("/tickets/new", methods=["GET", "POST"])
    def create_ticket_page():
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        if request.method == "GET":
            return render_template("create_ticket.html", error=None, success=None)
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        priority = request.form.get("priority", "medium")
        if not title or not description:
            return render_template("create_ticket.html", error="Title and description are required", success=None)
        now = datetime.now(timezone.utc).isoformat()
        ticket_id = str(uuid.uuid4())[:8]
        db = get_db()
        db.execute(
            "INSERT INTO tickets (id, title, description, priority, status, category, created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'open', 'general', ?, ?, ?)",
            (ticket_id, title, description, priority, session["user_id"], now, now),
        )
        db.commit()
        return render_template("create_ticket.html", error=None, success="Ticket created successfully!")

    @app.route("/logout")
    def logout_page():
        session.clear()
        return redirect(url_for("login_page"))

    # ── Health check ──────────────────────────────────────────────────
    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"}), 200

    init_db(app)
    return app


if __name__ == "__main__":
    application = create_app()
    port = int(os.getenv("PORT", 8080))
    application.run(host="0.0.0.0", port=port, debug=False)
