from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder=".", static_url_path="")

BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("APP_DATA_DIR", str(BASE_DIR))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATA_FILE = DATA_DIR / "notifications.json"
TEAMS_FILE = DATA_DIR / "teams.json"
DATA_LOCK = Lock()

DEFAULT_TEAMS = [
    {"code": "team-a", "displayName": "Equipe A", "password": "1234"},
    {"code": "team-b", "displayName": "Equipe B", "password": "1234"},
    {"code": "team-c", "displayName": "Equipe C", "password": "1234"},
]

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
ADMIN_SESSIONS: dict[str, datetime] = {}
SESSION_TTL_MINUTES = 480


def _load_teams() -> list[dict]:
    if not TEAMS_FILE.exists():
        TEAMS_FILE.write_text(json.dumps(DEFAULT_TEAMS, ensure_ascii=True, indent=2), encoding="utf-8")
        return DEFAULT_TEAMS.copy()

    try:
        loaded = json.loads(TEAMS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        loaded = []

    if not isinstance(loaded, list):
        return []

    teams: list[dict] = []
    for item in loaded:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "")).strip()
        name = str(item.get("displayName", "")).strip()
        password = str(item.get("password", ""))
        if code and name and password:
            teams.append({"code": code, "displayName": name, "password": password})

    return teams


def _save_teams(teams: list[dict]) -> None:
    TEAMS_FILE.write_text(json.dumps(teams, ensure_ascii=True, indent=2), encoding="utf-8")


def _team_lookup(teams: list[dict]) -> dict[str, dict[str, str]]:
    return {item["code"]: item for item in teams}


def _extract_admin_token() -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("X-Admin-Token", "").strip()


def _is_admin_authenticated() -> bool:
    token = _extract_admin_token()
    if not token:
        return False

    now = datetime.now(tz=timezone.utc)
    expiry = ADMIN_SESSIONS.get(token)
    if expiry is None:
        return False

    if expiry <= now:
        ADMIN_SESSIONS.pop(token, None)
        return False

    return True


def _load_notifications() -> list[dict]:
    if not DATA_FILE.exists():
        return []

    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _save_notifications(notifications: list[dict]) -> None:
    DATA_FILE.write_text(json.dumps(notifications, ensure_ascii=True, indent=2), encoding="utf-8")


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "utc": datetime.now(tz=timezone.utc).isoformat()})


@app.post("/api/admin/login")
def admin_login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))

    if username != ADMIN_USERNAME or password != ADMIN_PASSWORD:
        return jsonify({"error": "Invalid admin credentials"}), 401

    token = secrets.token_urlsafe(32)
    expiry = datetime.now(tz=timezone.utc).replace(microsecond=0) + timedelta(minutes=SESSION_TTL_MINUTES)
    ADMIN_SESSIONS[token] = expiry
    return jsonify({"token": token, "expiresAtUtc": expiry.isoformat()})


@app.get("/api/teams")
def get_teams():
    with DATA_LOCK:
        teams = _load_teams()
    teams = [{"code": item["code"], "displayName": item["displayName"]} for item in teams]
    return jsonify(teams)


@app.post("/api/admin/teams")
def create_team():
    if not _is_admin_authenticated():
        return jsonify({"error": "Admin authentication required"}), 401

    payload = request.get_json(silent=True) or {}
    code = str(payload.get("code", "")).strip().lower()
    display_name = str(payload.get("displayName", "")).strip()
    password = str(payload.get("password", ""))

    if not code or not display_name or not password:
        return jsonify({"error": "code, displayName and password are required"}), 400

    with DATA_LOCK:
        teams = _load_teams()
        lookup = _team_lookup(teams)
        if code in lookup:
            return jsonify({"error": "Team already exists"}), 409

        created = {"code": code, "displayName": display_name, "password": password}
        teams.append(created)
        _save_teams(teams)

    return jsonify({"code": code, "displayName": display_name}), 201


@app.post("/api/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    team_code = str(payload.get("teamCode", "")).strip()
    password = str(payload.get("password", ""))

    with DATA_LOCK:
        teams = _load_teams()
    team = _team_lookup(teams).get(team_code)
    if team is None or team["password"] != password:
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({"teamCode": team["code"], "teamName": team["displayName"]})


@app.get("/api/notifications")
def get_notifications():
    team_code = request.args.get("teamCode", "").strip()
    if not team_code:
        return jsonify({"error": "teamCode is required"}), 400

    after_id = request.args.get("afterId", default=0, type=int)
    limit = request.args.get("limit", default=100, type=int)
    limit = max(1, min(limit, 200))

    with DATA_LOCK:
        notifications = _load_notifications()

    filtered = [
        item
        for item in notifications
        if item.get("teamCode") == team_code and int(item.get("id", 0)) > after_id
    ]

    filtered.sort(key=lambda item: int(item.get("id", 0)), reverse=True)
    return jsonify(filtered[:limit])


@app.post("/api/notifications")
def create_notification():
    if not _is_admin_authenticated():
        return jsonify({"error": "Admin authentication required"}), 401

    payload = request.get_json(silent=True) or {}
    team_code = str(payload.get("teamCode", "")).strip()
    title = str(payload.get("title", "")).strip()
    message = str(payload.get("message", "")).strip()

    if not team_code or not title or not message:
        return jsonify({"error": "teamCode, title and message are required"}), 400

    with DATA_LOCK:
        teams = _load_teams()
    if team_code not in _team_lookup(teams):
        return jsonify({"error": "Unknown team"}), 400

    with DATA_LOCK:
        notifications = _load_notifications()
        next_id = max((int(item.get("id", 0)) for item in notifications), default=0) + 1
        created = {
            "id": next_id,
            "teamCode": team_code,
            "title": title,
            "message": message,
            "sentAtUtc": datetime.now(tz=timezone.utc).isoformat(),
        }
        notifications.append(created)
        _save_notifications(notifications)

    return jsonify(created), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
