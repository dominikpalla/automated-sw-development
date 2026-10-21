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
          * <entity>.py – Python class with attributes
          * <entity>_storage.py – in-memory list/dict with auto-incrementing ID
          * <entity>_routes.py – a module exposing CRUD handler functions and a routes dictionary.
            - Each handler must be a plain function (no Flask Blueprint).
            - Handlers should follow this convention:
                def list_handler(_=None): ...
                def add_handler(_=None): ...
                def edit_handler(id): ...
                def delete_handler(id): ...
            - At the end of the file, export a dictionary mapping action names to handlers:
                routes = {{
                    "list": list_handler,
                    "add": add_handler,
                    "edit": edit_handler,
                    "delete": delete_handler
                }}
            - Each handler must return Flask responses using render_template, redirect, etc.
            - IMPORTANT:
                * Do NOT hardcode the entity name in route decorators (manager adds /<entity>/ prefix).
                * When rendering templates, always use:
                    render_template("<entity>/list.html", ...)
                    render_template("<entity>/form.html", ...)
                * After add/edit/delete, always redirect to the list view at /<entity>/list
                  (never to just /<entity>).
                  Example: return redirect(f"/customer/list")
          * templates/<entity>/ folder containing:
              - list.html (Bootstrap table of records)
              - form.html (Bootstrap form for add/edit)
        - Template rules:
            * Every template must use hardcoded URLs like /<entity>/add, /<entity>/edit/{{id}}, /<entity>/delete/{{id}}
              instead of url_for.
            * Example: <a href="/customer/add">Add</a>, not {{ '{{ url_for("customer_add") }}' }}.
        - Use only in-memory storage. But structure code so DB layer could replace it later.
        - Relationships (if given) must be reflected with foreign keys (e.g., Car has customer_id).
        - Use Bootstrap for HTML styling.
        - Output MUST be a valid JSON object mapping relative filenames (with subfolders) to file contents.
          Example:
          {{
            "customer/customer.py": "...",
            "customer/customer_storage.py": "...",
            "customer/customer_routes.py": "...",
            "customer/templates/customer/list.html": "...",
            "customer/templates/customer/form.html": "..."
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

    def apply_feedback(self, spec, artefacts, feedback):
        """
        Apply feedback instructions to existing artefacts using LLM.
        Input:
            spec: str | dict - original specification
            artefacts: dict - {"filename": "content", ...}
            feedback: dict - {"instructions": [...]}
        Output:
            dict - {"filename": "corrected content", ...}
        """
        prompt = f"""
        You are a code repair assistant.

        TASK:
        Fix the following generated artefacts according to the FEEDBACK instructions.

        REQUIREMENT:
        {json.dumps(spec, indent=2) if isinstance(spec, dict) else spec}

        FEEDBACK:
        {json.dumps(feedback, indent=2)}

        CURRENT IMPLEMENTATION:
        {json.dumps(artefacts, indent=2)}

        STRICT RULES:
        1. Modify ONLY what is necessary to satisfy the feedback.
        2. Keep all filenames identical and unchanged.
        3. For each file, return the FULL corrected file content as a SINGLE STRING value.
        4. Do NOT split content into lists, arrays, or line-based pieces. 
           Every JSON value MUST be exactly one long string.
        5. The final answer MUST be a VALID JSON object in the following exact format:
           {{
             "filename1.py": "entire corrected file as one string",
             "filename2.html": "entire corrected file as one string"
           }}
        6. Do NOT include explanations, comments, Markdown code fences, or any text outside the JSON object.
        7. If unsure, return the best guess, but ALWAYS obey the output format exactly.
        """

        resp = self.client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        raw = resp.choices[0].message.content.strip()
        try:
            artefacts = json.loads(raw)
        except Exception as e:
            return {"status": "error", "message": f"Failed to parse JSON from LLM: {e}", "raw": raw}

        # Save artefacts back to disk (stejně jako v generate_crud_app)
        saved_files = []
        for fname, code in artefacts.items():
            clean_fname = fname
            if clean_fname.startswith("modules/"):
                clean_fname = clean_fname[len("modules/"):]
            path = self.modules_dir / clean_fname
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code, encoding="utf-8")
            saved_files.append(str(path.relative_to(self.modules_dir)))
            self.ensure_init_py(path.parent)

        return {
            "status": "ok",
            "artefacts": saved_files
        }




