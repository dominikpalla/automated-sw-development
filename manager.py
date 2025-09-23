# manager.py
"""
Manager (Flask app)
-------------------
Coordinates the cycle:
Interpreter -> (UMLTranslator) -> CodeGen.

Also serves:
- Chat UI: /
- Generated modules overview: /generated
- API endpoints: /interpreter/*, /uml/translate, /codegen/run
"""

from flask import Flask, request, jsonify, render_template
from pathlib import Path
from dotenv import load_dotenv
import os, json, importlib.util

from interpreter import Interpreter
from uml_translator import UMLTranslator
from codegen import CodeGen

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


# -------------------------
# Helpers
# -------------------------
def register_generated_modules(app, modules_dir: Path):
    """
    Dynamically load *_routes.py from each entity folder in modules/
    and register their Blueprint.
    Each *_routes.py must define: bp = Blueprint("<entity>", __name__)
    """
    for file in modules_dir.glob("*/*_routes.py"):
        module_name = file.stem
        spec = importlib.util.spec_from_file_location(module_name, file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "bp"):
            entity = module_name.replace("_routes", "")
            # url prefix = /<entity>
            app.register_blueprint(mod.bp, url_prefix=f"/{entity}")


def list_generated_entities(modules_dir: Path):
    """
    Collect entity names from *_routes.py files in modules/<entity>/.
    """
    entities = []
    for file in modules_dir.glob("*/*_routes.py"):
        entity = file.stem.replace("_routes", "")
        entities.append(entity)
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
# CodeGen
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

    # Return filenames + contents for preview
    files = {}
    for fname in out.get("artefacts", []):
        fpath = MODULES_DIR / fname
        if fpath.exists():
            files[fname] = fpath.read_text(encoding="utf-8")

    return jsonify({"status": out.get("status"), "files": files})


# -------------------------
# Start
# -------------------------
if __name__ == "__main__":
    # Register any already generated modules
    register_generated_modules(app, MODULES_DIR)

    app.run(host="0.0.0.0", port=8000, debug=True)
