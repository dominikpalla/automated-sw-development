# feedback.py
"""
Feedback module
---------------
- Receives original specification + artefacts + validation results
- Asks AI: "describe how to fix the errors"
- Returns INSTRUCTIONS, not code.
- Instructions are then passed to CodeGen (repair mode).
- Also cleans up old entity folder so a new implementation can be generated.
"""

import os
import json
import shutil
from pathlib import Path
from openai import OpenAI


class Feedback:
    def __init__(self, modules_dir="modules", dynamic_registry=None):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1")
        self.modules_dir = Path(modules_dir)
        # reference to dynamic registry so we can unregister entity routes
        self.dynamic_registry = dynamic_registry if dynamic_registry is not None else {}

    # -------------------------
    # Generate repair instructions from AI
    # -------------------------
    def generate_instructions(self, spec, artefacts, validation_result):
        """
        Ask AI to write step-by-step instructions for fixing validation issues.
        """
        prompt = f"""
        You are a senior software reviewer.
        The following CRUD implementation failed validation.

        SPECIFICATION:
        {json.dumps(spec, indent=2) if isinstance(spec, dict) else spec}

        VALIDATION RESULT:
        {json.dumps(validation_result, indent=2)}

        IMPLEMENTATION FILES (excerpt):
        {json.dumps({k: v[:500] for k, v in artefacts.items()}, indent=2)}
        (only first 500 chars of each file are shown to save space)

        TASK:
        - DO NOT return fixed code.
        - Instead, provide clear, structured repair instructions.
        - Refer explicitly to files and lines/sections if possible.
        - Use this format:

        {{
          "instructions": [
            "In file X.py: rename attribute 'foo' to 'bar' to match spec",
            "In file Y.html line 12: fix missing closing </tr> tag",
            "In Z_routes.py: after saving entity, redirect to /<entity>/list instead of /<entity>"
          ]
        }}
        """

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        reply = resp.choices[0].message.content.strip()

        try:
            return json.loads(reply)
        except Exception:
            return {"instructions": [reply]}



    # -------------------------
    # Apply fix (prepare payload for CodeGen)
    # -------------------------
    def apply_fix(self, spec, artefacts, feedback):
        """
        - Return payload for CodeGen fix
        """

        return {
            "mode": "fix",
            "spec": spec,
            "artefacts": artefacts,
            "feedback": feedback
        }
