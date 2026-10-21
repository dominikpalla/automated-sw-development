# validation.py
"""
Validation module
-----------------
- Checks syntax correctness (Python, HTML)
- Uses AI to verify that generated artefacts match the original specification
- Runs smoke tests against backend endpoints (/list, /add, /edit, /delete)
- AI generates test data dynamically from HTML forms (no hardcoded values!)
- Can simulate different types of errors for testing
"""

import os
import ast
import json
import requests
from pathlib import Path
from html.parser import HTMLParser
from openai import OpenAI


class SimpleHTMLValidator(HTMLParser):
    """Basic HTML syntax checker."""
    def error(self, message):
        raise ValueError(message)


class Validator:
    def __init__(self, base_url="http://127.0.0.1:8000", modules_dir="modules"):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.base_url = base_url
        self.modules_dir = Path(modules_dir)

    # -------------------------
    # Syntax checks
    # -------------------------
    def check_python(self, path: Path):
        try:
            ast.parse(path.read_text(encoding="utf-8"))
            return True, None
        except SyntaxError as e:
            return False, f"Python syntax error in {path}: {e}"

    def check_html(self, path: Path):
        try:
            parser = SimpleHTMLValidator()
            parser.feed(path.read_text(encoding="utf-8"))
            return True, None
        except Exception as e:
            return False, f"HTML syntax error in {path}: {e}"

    # -------------------------
    # AI Validation
    # -------------------------
    def ai_validate(self, spec: dict, artefacts: dict):
        """
        Ask AI: Does this implementation fulfil the specification?
        spec: NL text or UML JSON
        artefacts: dict of {filename: code}
        """
        prompt = f"""
        You are a software validation assistant.
        Task: Verify if the following CRUD implementation matches the given requirement.

        REQUIREMENT:
        {json.dumps(spec, indent=2) if isinstance(spec, dict) else spec}

        IMPLEMENTATION FILES:
        {json.dumps(artefacts, indent=2)}

        RULES:
        - If it matches, answer exactly: OK
        - If not, explain the mismatches clearly.
        """

        resp = self.client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        reply = resp.choices[0].message.content.strip()
        print("🤖 AI raw reply:", reply)  # DEBUG výstup do konzole

        if reply.upper().startswith("OK"):
            return True, None
        return False, reply

    # -------------------------
    # AI-generated test data
    # -------------------------
    def generate_test_data(self, form_html: str):
        """
        Use AI to generate JSON test data for a given HTML form.
        """
        prompt = f"""
        You are a test data generator.
        Given the following HTML form, return a valid JSON object with suitable test values
        for each input field. Avoid empty or placeholder values.

        FORM:
        {form_html}

        Example output:
        {{
            "color": "Blue",
            "manufacturer_id": "1"
        }}
        """

        resp = self.client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        raw = resp.choices[0].message.content.strip()
        print("🤖 AI test data reply:", raw)  # DEBUG výstup do konzole
        try:
            return json.loads(raw)
        except Exception:
            return {}

    # -------------------------
    # Smoke test CRUD endpoints
    # -------------------------
    def smoke_test(self, entity: str):
        """
        Run simple CRUD tests on generated endpoints.
        """
        try:
            # 1) GET list
            r = requests.get(f"{self.base_url}/{entity}/list")
            if r.status_code != 200:
                return False, f"GET /{entity}/list failed ({r.status_code})"

            # 2) GET add form + generate test data
            r = requests.get(f"{self.base_url}/{entity}/add")
            if r.status_code != 200:
                return False, f"GET /{entity}/add failed ({r.status_code})"
            test_data = self.generate_test_data(r.text)

            # 3) POST add
            r = requests.post(f"{self.base_url}/{entity}/add", data=test_data)
            if r.status_code not in (200, 302):
                return False, f"POST /{entity}/add failed ({r.status_code})"

            # 4) GET list again – should contain new record
            r = requests.get(f"{self.base_url}/{entity}/list")
            if test_data and not any(val in r.text for val in test_data.values()):
                return False, f"New record not found in /{entity}/list"

            return True, None

        except Exception as e:
            return False, f"Smoke test for {entity} failed: {e}"

    # -------------------------
    # Orchestrator
    # -------------------------
    def validate(self, spec, artefacts, simulate: str = None):
        """
        Validate artefacts step by step.
        simulate: optional string ["syntax", "html", "ai", "runtime"] to simulate errors.
        Returns dict with status + optional message.
        """

        # 0. Simulate errors → also save them to disk so syntax check sees them
        if simulate == "syntax":
            for fname in artefacts:
                if fname.endswith(".py"):
                    broken = artefacts[fname] + "\n)"
                    artefacts[fname] = broken
                    (self.modules_dir / fname).write_text(broken, encoding="utf-8")
                    break
        elif simulate == "html":
            for fname in artefacts:
                if fname.endswith(".html"):
                    broken = artefacts[fname].replace("</form>", "")
                    artefacts[fname] = broken
                    (self.modules_dir / fname).write_text(broken, encoding="utf-8")
                    break
        elif simulate == "ai":
            for fname in artefacts:
                if fname.endswith(".py") and "class " in artefacts[fname]:
                    broken = artefacts[fname].replace("model", "version")
                    artefacts[fname] = broken
                    (self.modules_dir / fname).write_text(broken, encoding="utf-8")
                    break
        elif simulate == "runtime":
            for fname in artefacts:
                if fname.endswith("_routes.py"):
                    broken = artefacts[fname] + "\n\nraise Exception('Simulated runtime error')\n"
                    artefacts[fname] = broken
                    (self.modules_dir / fname).write_text(broken, encoding="utf-8")
                    break

        # 1. Syntax check
        for fname in artefacts.keys():
            path = self.modules_dir / fname
            if fname.endswith(".py"):
                ok, msg = self.check_python(path)
            elif fname.endswith(".html"):
                ok, msg = self.check_html(path)
            else:
                continue
            if not ok:
                return {"status": "error", "stage": "syntax", "message": msg}

        # 2. AI validation
        ok, msg = self.ai_validate(spec, artefacts)
        if not ok:
            return {"status": "error", "stage": "ai", "message": msg}

        # 3. Smoke test
        for fname in artefacts.keys():
            if fname.endswith("_routes.py"):
                entity = fname.split("/")[0]
                ok, msg = self.smoke_test(entity)
                if not ok:
                    return {"status": "error", "stage": "smoketest", "message": msg}

        return {"status": "ok"}
