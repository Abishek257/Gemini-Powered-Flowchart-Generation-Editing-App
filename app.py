from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, abort
import backend
import os
import uuid
from pathlib import Path
from datetime import datetime

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "defaultsecret")

SESSION_DIR = backend.SESSION_DIR


# -------------------- Helper Functions --------------------

def _safe_json_path(session_id: str) -> Path:
    """Return the path to a JSON file, user-specific if applicable."""
    user_email = session.get("email")
    if user_email:
        safe_email = user_email.replace("@", "_at_").replace(".", "_dot_")
        matches = list(SESSION_DIR.glob(f"{safe_email}__{session_id}.json"))
        if matches:
            return matches[0]
    # fallback for legacy files
    return SESSION_DIR / f"{session_id}.json"


def _summarize_file(p: Path):
    """Extracts metadata for history listing."""
    try:
        stat = p.stat()
        dt = datetime.fromtimestamp(stat.st_mtime)
        data = backend.json.loads(p.read_text(encoding="utf-8"))
        title = ""
        nda = data.get("nodeDataArray", [])
        if nda:
            title = (nda[0].get("text") or "").strip()
        return {
            "session_id": p.stem.split("__")[-1],
            "title": title or "Untitled flowchart",
            "updated_iso": dt.isoformat(),
            "updated_date": dt.strftime("%Y-%m-%d"),
            "size_kb": round(stat.st_size / 1024, 1),
        }
    except Exception:
        return None


# -------------------- Auth --------------------

@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = request.form.get("email")
        role = request.form.get("role")
        if not email or not role:
            error = "Please enter email and role"
        else:
            session["email"] = email
            session["role"] = role
            return redirect(url_for("dashboard"))
    return render_template("login.html", error=error)


@app.route("/dashboard")
def dashboard():
    if "email" not in session:
        return redirect(url_for("login"))
    role = session.get("role")
    templates = backend.list_templates_for_role(role)
    return render_template("dashboard.html", role=role, templates=templates)


@app.route("/full_instruction")
def full_instruction():
    if "email" not in session:
        return redirect(url_for("login"))
    return render_template("full_instruction.html")


@app.route("/chat_mode")
def chat_mode():
    if "email" not in session:
        return redirect(url_for("login"))
    return render_template("chat_mode.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -------------------- Flowchart APIs --------------------

@app.route("/flowchart/generate", methods=["POST"])
def generate_flowchart():
    data = request.get_json(force=True)
    prompt = data.get("prompt", "")
    model_json = backend.generate_json(prompt)
    session_id = str(uuid.uuid4())
    backend.save_json(session_id, model_json, session.get("email"))
    return jsonify({"json": model_json, "session_id": session_id})


@app.route("/flowchart/modify", methods=["POST"])
def modify_flowchart():
    data = request.get_json(force=True)
    session_id = data.get("session_id")
    instruction = data.get("instruction")
    if not session_id:
        return jsonify({"error": "session_id required"}), 400
    model_json = backend.modify_json(session_id, instruction, session.get("email"))
    return jsonify({"json": model_json, "session_id": session_id})


@app.route("/flowchart/save", methods=["POST"])
def save_flowchart():
    data = request.get_json(force=True)
    session_id = data.get("session_id")
    model_json = data.get("json")
    if not session_id or model_json is None:
        return jsonify({"error": "session_id and json required"}), 400
    backend.save_json(session_id, model_json, session.get("email"))
    return jsonify({"status": "saved"})


@app.route("/flowchart/load", methods=["POST"])
def load_flowchart():
    data = request.get_json(force=True)
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "session_id required"}), 400
    model_json = backend.load_json(session_id, session.get("email"))
    return jsonify({"json": model_json})


# -------------------- History APIs --------------------

@app.route("/history/list")
def history_list():
    user_email = session.get("email")
    if not user_email:
        return jsonify({"days": {}})

    safe_email = user_email.replace("@", "_at_").replace(".", "_dot_")
    pattern = f"{safe_email}__*.json"

    items = []
    for p in SESSION_DIR.glob(pattern):
        s = _summarize_file(p)
        if s:
            items.append(s)

    grouped = {}
    for it in sorted(items, key=lambda x: x["updated_iso"], reverse=True):
        grouped.setdefault(it["updated_date"], []).append(it)

    return jsonify({"days": grouped})


@app.route("/history/open/<session_id>")
def history_open(session_id):
    p = _safe_json_path(session_id)
    if not p.exists():
        return jsonify({"error": "not found"}), 404
    data = backend.load_json(session_id, session.get("email"))
    return jsonify({"json": data, "session_id": session_id})


@app.route("/history/download/<session_id>")
def history_download(session_id):
    p = _safe_json_path(session_id)
    if not p.exists():
        abort(404)
    return send_file(
        p,
        mimetype="application/json",
        as_attachment=True,
        download_name=f"{session_id}.json",
    )


@app.route("/history/delete/<session_id>", methods=["DELETE"])
def history_delete(session_id):
    p = _safe_json_path(session_id)
    if not p.exists():
        return jsonify({"status": "ok"}), 200
    p.unlink(missing_ok=True)
    return jsonify({"status": "deleted", "session_id": session_id})


# -------------------- Template APIs --------------------

@app.route("/templates/list")
def list_templates():
    role = session.get("role")
    templates = backend.list_templates_for_role(role)
    return jsonify({"templates": templates})


@app.route("/templates/load/<name>")
def load_template(name):
    result = backend.load_template(name)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)
