import os
from pathlib import Path
import google.generativeai as genai
from dotenv import load_dotenv
import json
import uuid

load_dotenv()

# Google Gemini setup
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise RuntimeError("GOOGLE_API_KEY missing in .env")

genai.configure(api_key=api_key)
MODEL = genai.GenerativeModel("gemini-flash-latest")

# Directories
BASE_DIR = Path(__file__).resolve().parent
SESSION_DIR = BASE_DIR / "session_files"
SESSION_DIR.mkdir(exist_ok=True)

TEMPLATE_DIR = BASE_DIR / "templates_data"
TEMPLATE_DIR.mkdir(exist_ok=True)


# -------------------- Gemini --------------------

def generate_json(prompt: str) -> dict:
    system_prompt = """
You are a STRICT flowchart generator for GoJS.
Rules:
- Respond ONLY with valid JSON for GoJS model.
- JSON MUST have "nodeDataArray" and "linkDataArray".
- Each node must include: { "key": int, "text": string, "loc": "x y", "shape": string }.
- Supported shapes: RoundedRectangle, Ellipse, Diamond, Parallelogram.
- Each link must include: { "from": key, "to": key, "text": optional label }.
- Do NOT include explanations or text.
"""
    response = MODEL.generate_content(system_prompt + "\nUser prompt: " + prompt)
    text = (response.text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        return {"nodeDataArray": [], "linkDataArray": []}


def modify_json(session_id: str, instruction: str, user_email: str = None) -> dict:
    """Modify existing flowchart based on instruction."""
    current = load_json(session_id, user_email)
    system_prompt = """
You are a STRICT flowchart editor for GoJS.
Rules:
- You will receive existing GoJS JSON and a user instruction.
- Modify ONLY according to the instruction.
- Keep nodeDataArray and linkDataArray intact unless instructed.
- Ensure every node has "key", "text", "loc", "shape".
- Supported shapes: RoundedRectangle, Ellipse, Diamond, Parallelogram.
- Return ONLY valid JSON.
"""
    response = MODEL.generate_content(
        system_prompt + "\nCurrent JSON:\n" + json.dumps(current) + "\nInstruction: " + instruction
    )
    text = (response.text or "").strip()
    try:
        data = json.loads(text)
    except Exception:
        data = current
    save_json(session_id, data, user_email)
    return data


# -------------------- Persistence --------------------

def save_json(session_id: str, data: dict, user_email: str = None):
    """Save flowchart JSON (namespaced by user email)."""
    if user_email:
        safe_email = user_email.replace("@", "_at_").replace(".", "_dot_")
        path = SESSION_DIR / f"{safe_email}__{session_id}.json"
    else:
        path = SESSION_DIR / f"{session_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(session_id: str, user_email: str = None) -> dict:
    """Load a JSON file, prefixed with user email if available."""
    path = None
    if user_email:
        safe_email = user_email.replace("@", "_at_").replace(".", "_dot_")
        matches = list(SESSION_DIR.glob(f"{safe_email}__{session_id}.json"))
        if matches:
            path = matches[0]
    if not path:
        path = SESSION_DIR / f"{session_id}.json"
    if not path.exists():
        return {"nodeDataArray": [], "linkDataArray": []}
    return json.loads(path.read_text(encoding="utf-8"))


# -------------------- Templates --------------------

def list_templates() -> list:
    """Return all available template names (without .json)."""
    return [f.stem for f in TEMPLATE_DIR.glob("*.json")]


def load_template(name: str) -> dict:
    """Load a JSON template from templates_data/."""
    file_path = TEMPLATE_DIR / f"{name}.json"
    if not file_path.exists():
        return {"error": f"Template '{name}' not found"}
    try:
        template = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": f"Invalid template JSON: {e}"}

    session_id = str(uuid.uuid4())
    save_json(session_id, template)
    return {"session_id": session_id, "json": template, "template": name}


def list_templates_for_role(role: str) -> list:
    """Return template names filtered by user role."""
    all_templates = [f.stem for f in TEMPLATE_DIR.glob("*.json")]

    role_map = {
        "NPI": ["warehouse", "smt_top", "smt_bottom"],
        "Quality": ["wave_soldering", "selective_soldering"],
    }

    allowed = role_map.get(role, [])
    return [t for t in all_templates if t in allowed]
