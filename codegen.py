"""
CodeGen module
--------------
Generates CRUD artefacts for Mini GAI CRM.

Behaviour:
- NL mode: AI model generates artefacts based on free-form requirement text.
- UML mode: AI model generates artefacts based on UML JSON specification.
- Repair mode: (future) AI minimally fixes artefacts.

Output structure (per entity):
modules/
  <entity>/
    app.py
    <entity>.py
    <entity>_storage.py
    <entity>_routes.py
    templates/
      list.html
      form.html
"""

import os, json
from pathlib import Path
from openai import OpenAI


class CodeGen:
    def __init__(self, metadata_path: Path, modules_dir: Path):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1")
        self.modules_dir = Path(modules_dir)
        self.modules_dir.mkdir(exist_ok=True)
        # zajistí __init__.py v root modules/
        self.ensure_init_py(self.modules_dir)

    @staticmethod
    def ensure_init_py(path: Path):
        """Ensure __init__.py exists in given folder."""
        path = Path(path)
        init_path = path / "__init__.py"
        if not init_path.exists():
            init_path.write_text("# auto-generated init\n", encoding="utf-8")

    def generate_crud_app(self, payload: dict) -> dict:
        """
        Generate CRUD artefacts from either NL summary or UML JSON spec.
        Saves artefacts into modules/<entity>/ directories.
        NOTE: Uses in-memory storage (lists/dicts).
              Structure can be extended to use a real DB later.
        """
        if payload.get("mode") == "nl":
            spec = payload.get("text", "")
            mode_str = f"Natural language requirement:\n{spec}"
        elif payload.get("mode") == "uml":
            spec = json.dumps(payload.get("json", {}), indent=2)
            mode_str = f"UML JSON specification:\n{spec}"
        else:
            return {"status": "error", "message": "Unsupported mode"}

        prompt = f"""
You are a software generator. Based on the following requirement/specification,
generate a minimal CRUD web app in Python Flask with in-memory storage.

{mode_str}

REQUIREMENTS:
- For each entity, create a dedicated folder inside modules/, named after the entity (lowercase).
  Example: modules/customer/
- Inside that folder include:
  * app.py – minimal Flask app that imports and registers the Blueprint, runs on port 8000
  * <entity>.py – Python class with attributes
  * <entity>_storage.py – in-memory list/dict with auto-incrementing ID
  * <entity>_routes.py – Flask Blueprint exposing CRUD routes:
    - /list
    - /add
    - /edit/<id>
    - /delete/<id>
    Must define and export:
      bp = Blueprint("<entity>", __name__, 
                     template_folder=os.path.join(os.path.dirname(__file__), "templates"))
    IMPORTANT: Do NOT include the entity name in the route paths. 
    The manager will handle prefixing the routes with /<entity>.
  * templates/ folder containing:
      - list.html (Bootstrap table of records)
      - form.html (Bootstrap form for add/edit)
- Use only in-memory storage. But structure code so DB layer could replace it later.
- Relationships (if given) must be reflected with foreign keys (e.g., Car has customer_id).
- Use Bootstrap for HTML styling.
- Output MUST be a valid JSON object mapping relative filenames (with subfolders) to file contents.
  Example:
  {{
    "customer/app.py": "...",
    "customer/customer.py": "...",
    "customer/customer_storage.py": "...",
    "customer/customer_routes.py": "...",
    "customer/templates/list.html": "...",
    "customer/templates/form.html": "..."
  }}
- Do NOT include explanations, code fences, or text outside JSON.
"""

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        content = (resp.choices[0].message.content or "").strip()
        # strip possible code fences
        if content.startswith("```"):
            content = content.split("```", 1)[-1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        try:
            artefacts = json.loads(content)
        except Exception as e:
            return {"status": "error", "message": f"Invalid JSON from AI: {e}", "raw": content}

        # Save artefacts into entity-specific folders under modules/
        saved_files = []
        for fname, code in artefacts.items():
            clean_fname = fname
            if clean_fname.startswith("modules/"):
                clean_fname = clean_fname[len("modules/"):]  # odřízne první "modules/"
            path = self.modules_dir / clean_fname
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code, encoding="utf-8")
            saved_files.append(str(path.relative_to(self.modules_dir)))
            # zajistí __init__.py v každém adresáři
            self.ensure_init_py(path.parent)

        return {
            "status": "ok",
            "artefacts": saved_files
        }
