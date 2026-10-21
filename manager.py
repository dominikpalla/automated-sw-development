"""
Manager (Flask app)
-------------------
Coordinates the cycle:
Interpreter -> (UMLTranslator) -> CodeGen -> Validator (+ Feedback).

Also serves:
- Chat UI: /
- Generated modules overview: /generated
- API endpoints: /interpreter/*, /uml/translate, /codegen/run, /validate/run
- Dynamic dispatcher for generated entity routes
"""

from flask import Flask, request, jsonify, render_template
from pathlib import Path
from dotenv import load_dotenv
import os, json, importlib
import shutil

from jinja2 import ChoiceLoader, FileSystemLoader

from interpreter import Interpreter
from uml_translator import UMLTranslator
from codegen import CodeGen
from validation import Validator
from feedback import Feedback

# -------------------------
# Setup
# -------------------------
load_dotenv()
app = Flask(__name__, template_folder="templates", static_folder="static")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
METADATA_PATH = DATA_DIR / "metadata.json"
MODULES_DIR = Path("modules")
MODULES_DIR.mkdir(exist_ok=True)

interpreter = Interpreter(METADATA_PATH)
uml_translator = UMLTranslator()
codegen = CodeGen(METADATA_PATH, MODULES_DIR)
validator = Validator(base_url="http://127.0.0.1:8000", modules_dir=MODULES_DIR)
feedback = Feedback()

SIM = None #"ai"

# -------------------------
# Jinja loader refresh
# -------------------------
def refresh_template_loader():
    """
    Reload Jinja template search paths so new entity templates are picked up
    without restarting the server.
    """
    extra_template_paths = []
    for entity_dir in MODULES_DIR.glob("*"):
        tdir = entity_dir / "templates"
        if tdir.exists():
            extra_template_paths.append(str(tdir))

    if extra_template_paths:
        app.jinja_loader = ChoiceLoader(
            [app.jinja_loader] + [FileSystemLoader(p) for p in extra_template_paths]
        )
        print(f"🔄 Refreshed template loader with: {extra_template_paths}")

# initial refresh at startup
refresh_template_loader()

# -------------------------
# Dynamic Dispatcher
# -------------------------
dynamic_registry = {}

def load_entity(entity: str):
    """
    Dynamically import <entity>_routes.py and store its routes dict.
    """
    try:
        module_path = f"modules.{entity}.{entity}_routes"
        mod = importlib.import_module(module_path)
        if hasattr(mod, "routes"):
            dynamic_registry[entity] = mod.routes
            print(f"✅ Loaded entity '{entity}' with routes: {list(mod.routes.keys())}")
        else:
            print(f"⚠️ Module {module_path} has no 'routes' dict.")
    except Exception as e:
        print(f"❌ Failed to load {entity}: {e}")


def get_entity_from_artefacts(artefacts: dict):
    for fname in artefacts.keys():
        parts = fname.split("/")
        if len(parts) > 1:
            return parts[0]
    return None


def cleanup_entity(entity: str):
    """Remove entity folder from modules/ and unregister it from dynamic routes."""
    target = MODULES_DIR / entity
    print(f"🧹 Trying to remove entity folder: {target}")
    if target.exists() and target.is_dir():
        shutil.rmtree(target)
        print(f"🗑️ Removed old entity folder: {target}")
    else:
        print(f"⚠️ Entity folder {target} not found")

    if entity in dynamic_registry:
        dynamic_registry.pop(entity, None)
        print(f"🔄 Unregistered entity '{entity}' from dynamic routes")


@app.route("/<entity>/<action>", methods=["GET", "POST"])
@app.route("/<entity>/<action>/<int:item_id>", methods=["GET", "POST"])
def dynamic_dispatch(entity, action, item_id=None):
    """
    Catch-all dispatcher for /<entity>/<action> URLs.
    Looks up the handler function in dynamic_registry.
    """
    if entity not in dynamic_registry:
        load_entity(entity)

    routes = dynamic_registry.get(entity, {})
    handler = routes.get(action)

    if not handler:
        return f"No route '{action}' for entity '{entity}'", 404

    return handler(item_id) if item_id is not None else handler()

def list_generated_entities(modules_dir: Path):
    """
    Collect entity names from *_routes.py files in modules/<entity>/.
    """
    entities = []
    for file in modules_dir.glob("*/*_routes.py"):
        entities.append(file.parent.name)
    return entities

# -------------------------
# Views
# -------------------------
@app.get("/")
def index_view():
    return render_template("index.html")

@app.get("/generated")
def generated_index():
    """Show list of generated entities with CRUD links"""
    entities = list_generated_entities(MODULES_DIR)
    return render_template("generated_index.html", entities=entities)

# -------------------------
# Interpreter / UML
# -------------------------
@app.post("/interpreter/process")
def interpreter_process():
    payload = request.get_json(force=True)
    msg = payload.get("message", "")
    out = interpreter.process(msg)
    return jsonify(out)

@app.post("/interpreter/confirm")
def interpreter_confirm():
    out = interpreter.confirm()
    return jsonify(out)

@app.post("/uml/translate")
def uml_translate():
    payload = request.get_json(force=True)
    summary = payload.get("summary", "")
    out = uml_translator.translate(summary)
    return jsonify(out)

# -------------------------
# CodeGen (only generation)
# -------------------------
@app.post("/codegen/run")
def codegen_run():
    payload = request.get_json(force=True)
    mode = payload.get("mode", "nl")
    spec = payload.get("spec", "")
    if mode == "uml":
        spec = payload.get("spec_json", {})

    cg_in = {"mode": mode, "text": spec} if mode == "nl" else {"mode": "uml", "json": spec}
    out = codegen.generate_crud_app(cg_in)

    refresh_template_loader()

    # collect artefacts for preview
    files = {}
    for fname in out.get("artefacts", []):
        fpath = MODULES_DIR / fname
        if fpath.exists():
            files[fname] = fpath.read_text(encoding="utf-8")

    return jsonify({
        "status": out.get("status"),
        "files": files,
        "spec": spec
    })

# -------------------------
# Validation (separate step)
# -------------------------
@app.post("/validate/run")
def validate_run():
    global SIM
    payload = request.get_json(force=True)
    spec = payload.get("spec", "")
    files = payload.get("files", {})

    val_result = validator.validate(spec, files, simulate=SIM)

    if SIM == "ai":
        SIM = None

    feedback_instructions = None
    if val_result["status"] == "error":
        print("⚠️ Validation failed, generating repair instructions...")
        feedback_instructions = feedback.generate_instructions(spec, files, val_result)

    return jsonify({
        "validation": val_result,
        "feedback": feedback_instructions
    })

@app.post("/codegen/fix")
def codegen_fix():
    payload = request.get_json(force=True)
    spec = payload.get("spec", "")
    artefacts = payload.get("artefacts", {})
    fb = payload.get("feedback", {})

    entity = get_entity_from_artefacts(artefacts)
    if entity:
        cleanup_entity(entity)

    out = codegen.apply_feedback(spec, artefacts, fb)

    refresh_template_loader()

    files = {}
    if isinstance(out, dict):
        for fname, code in out.items():
            if isinstance(code, list):
                code = "\n".join(str(line) for line in code)
            elif not isinstance(code, str):
                code = str(code)

            path = MODULES_DIR / fname
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code, encoding="utf-8")
            files[fname] = code

    return jsonify({
        "status": "ok",
        "files": files,
        "spec": spec
    })







# -------------------------
# Start
# -------------------------
if __name__ == "__main__":
    print(f"📦 Available entities: {list_generated_entities(MODULES_DIR)}")
    app.run(host="0.0.0.0", port=8000, debug=True)
