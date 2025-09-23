# interpreter.py
from pathlib import Path
import os, json
from openai import OpenAI


class Interpreter:
    def __init__(self, metadata_path: Path):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1")
        self.metadata_path = metadata_path
        self.reset_state()

    def reset_state(self):
        self.state = {
            "requirement": None,
            "summaries": [],
            "clarifications": []
        }

    def process(self, message: str) -> dict:
        """
        Unified method: if it's the first message -> treat as start,
        otherwise refine with conversation history.
        """
        if not self.state["summaries"]:
            # first message = start
            self.state["requirement"] = message
            return self._ask_ai(self.state["requirement"])
        else:
            # next messages = refine
            self.state["clarifications"].append({"user": message})
            return self._ask_ai(
                self.state["requirement"],
                answers=self.state["clarifications"],
                summaries=self.state["summaries"]
            )

    def confirm(self) -> dict:
        """
        Finalize the conversation and reset interpreter state.
        """
        if not self.state["summaries"]:
            raise RuntimeError("No summary has been generated yet.")
        final_summary = self.state["summaries"][-1]
        self.reset_state()
        return {"status": "ok", "mode": "nl", "text": final_summary}

    def _ask_ai(self, requirement: str, answers=None, summaries=None) -> dict:
        """
        Internal: call AI model with full context.
        """
        answers_text = json.dumps(answers, indent=2) if answers else "[]"
        summaries_text = "\n".join([f"- {s}" for s in (summaries or [])])

        prompt = f"""
You are refining a clarified summary of a user requirement for a CRUD app.

Original requirement:
{requirement}

Previous summaries:
{summaries_text if summaries_text else "None yet"}

User clarifications so far:
{answers_text}

TASK:
1. Update the summary to reflect ALL clarifications so far (never restart from scratch).
2. If there are still ambiguities, list them as new clarification questions.
3. Always check for:
   - Unique ID for each entity (auto-generated or manual).
   - Data types of attributes (string, number, boolean, date, etc.).
   - Cardinality of relationships (1:1, 1:N, N:M).
   - Which attributes are required vs. optional.
   - UI hints (forms, select boxes, checkboxes).
4. Output valid JSON:
{{
  "summary": "string",
  "clarifications": ["q1", "q2", ...]
}}
"""

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        content = (resp.choices[0].message.content or "").strip()

        try:
            parsed = json.loads(content)
        except Exception:
            parsed = {"summary": requirement, "clarifications": []}

        self.state["summaries"].append(parsed.get("summary", requirement))

        return {
            "status": "incomplete" if parsed.get("clarifications") else "ok",
            "mode": "nl",
            "text": parsed.get("summary", requirement),
            "clarifications": parsed.get("clarifications", [])
        }

    def load_metadata(self):
        if self.metadata_path.exists():
            return json.loads(self.metadata_path.read_text(encoding="utf-8"))
        return {}
