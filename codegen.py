# cogen.py
import os
import json
from pathlib import Path
from openai import OpenAI


class CodeGen:
    """
    CodeGen generates or repairs artefacts:
    - NL mode: pass the requirement directly to the AI model with strict instructions.
    - UML mode: deterministic generation from UML JSON (with ui_hints).
    - Repair mode: artefacts + repair_prompt (from Feedback).
    """

    def __init__(self, metadata_path: Path, modules_dir: Path):
        self.metadata_path = Path(metadata_path)
        self.modules_dir = Path(modules_dir)
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1")

    # -------------------------
    # Main entry
    # -------------------------
    def generate(self, payload: dict):
        if "repair_prompt" in payload:
            return self._repair(payload)

        mode = payload.get("mode", "nl")
        if mode == "uml":
            return self._generate_from_uml(payload.get("json", {}))
        else:
            return self._generate_from_nl(payload.get("text", ""))

    # -------------------------
    # NL mode
    # -------------------------
    def _generate_from_nl(self, text: str):
        if not text:
            return {
                "status": "needs_clarification",
                "questions": ["Requirement text is empty. Please provide details."]
            }

        prompt = f"""
        You are an assistant that generates Python + HTML code artefacts.

        Requirement:
        {text}

        Instructions:
        - Generate Python classes (models) with attributes.
        - Generate CRUD operations (create, read, update, delete).
        - Generate simple HTML templates (forms, tables, lists).
        - If entities are related (e.g., Car belongs to Customer):
          - Add foreign key attributes in Python models.
          - In child entity forms, generate an HTML <select> dropdown
            to choose the related parent entity.
        - Do NOT use JavaScript or advanced frameworks.
        - Output must be a JSON object mapping filenames to code strings.
        """

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        content = resp.choices[0].message.content.strip()
        usage = {
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens
        }

        try:
            artefacts = json.loads(content)
        except Exception:
            return {
                "status": "error",
                "message": "Could not parse AI output into JSON.",
                "usage": usage
            }

        report = {
            "entities": [f.split(".")[0] for f in artefacts.keys() if f.endswith(".model.py")],
            "relations": [],  # handled heuristically by LLM in NL mode
            "files": list(artefacts.keys())
        }

        return {
            "status": "ok",
            "metadata_delta": {"entities": report["entities"], "relations": []},
            "artefacts": artefacts,
            "report": report,
            "usage": usage
        }

    # -------------------------
    # UML mode
    # -------------------------
    def _generate_from_uml(self, spec: dict):
        entities = [e["name"] for e in spec.get("entities", [])]
        relations = spec.get("relations", [])
        views = spec.get("views", [])

        artefacts = {}
        for ent in entities:
            artefacts[f"{ent}.model.py"] = self._template_model(ent, spec)
            artefacts[f"{ent}.form.html"] = self._template_form(ent, spec)

        metadata_delta = {"entities": entities, "relations": relations, "views": views}
        report = {"entities": entities, "relations": relations, "files": list(artefacts.keys())}

        usage = {
            "prompt_tokens": len(json.dumps(spec).split()),
            "completion_tokens": sum(len(c.split()) for c in artefacts.values())
        }

        return {
            "status": "ok",
            "metadata_delta": metadata_delta,
            "artefacts": artefacts,
            "report": report,
            "usage": usage
        }

    # -------------------------
    # Repair mode
    # -------------------------
    def _repair(self, payload: dict):
        artefacts = payload.get("artefacts", {})
        repair_prompt = payload.get("repair_prompt", "")

        if not artefacts or not repair_prompt:
            return {
                "status": "error",
                "message": "Repair requested but artefacts or prompt are missing."
            }

        prompt = f"""
        You are an assistant that repairs generated Python + HTML code artefacts.

        Repair instruction:
        {repair_prompt}

        Current artefacts:
        {json.dumps(artefacts, indent=2)}

        Task:
        - Modify only what is necessary to resolve the issue.
        - Keep CRUD logic and simple HTML forms intact.
        - Do not introduce JavaScript.
        - Return JSON mapping filenames to corrected code.
        """

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        content = resp.choices[0].message.content.strip()
        usage = {
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens
        }

        try:
            fixed = json.loads(content)
        except Exception:
            fixed = artefacts  # fallback if parsing fails

        report = {"entities": [], "relations": [], "files": list(fixed.keys())}

        return {
            "status": "ok",
            "metadata_delta": {},
            "artefacts": fixed,
            "report": report,
            "usage": usage
        }

    # -------------------------
    # Templates for UML mode
    # -------------------------
    def _template_model(self, entity: str, spec: dict):
        return f"""class {entity}:
    def __init__(self, id: int = None):
        self.id = id
"""

    def _template_form(self, entity: str, spec: dict):
        ent_spec = next((e for e in spec.get("entities", []) if e["name"] == entity), {})
        form_fields = ""

        # Default fields
        for attr in ent_spec.get("attributes", []):
            select_hint = None
            for sel in ent_spec.get("ui_hints", {}).get("select_fields", []):
                if sel["attribute"] == attr["name"]:
                    select_hint = sel
                    break

            if select_hint:
                target = select_hint["target_entity"]
                label = select_hint.get("label_attr", "id")
                form_fields += f"""
    <label for="{attr['name']}">{target}:</label>
    <select id="{attr['name']}" name="{attr['name']}" required>
        {{% for item in {target.lower()}s %}}
            <option value="{{{{ item.id }}}}">{{{{ item.{label} }}}}</option>
        {{% endfor %}}
    </select>
"""
            else:
                form_fields += f"""
    <label for="{attr['name']}">{attr['name'].capitalize()}:</label>
    <input type="text" id="{attr['name']}" name="{attr['name']}" required>
"""

        return f"""<form method="post" action="/{entity.lower()}/create">
    {form_fields}
    <button type="submit">Create {entity}</button>
</form>
"""
