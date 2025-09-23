# interpreter.py
import re
import json
from pathlib import Path


class Interpreter:
    """
    Interpreter normalizes user requirements and drives a clarify/confirm loop.
    - Always returns a paraphrased summary.
    - If critical details are missing, provides clarifying questions.
    - User can either accept the summary or provide clarification answers.
    """

    def __init__(self, metadata_path: Path):
        self.metadata_path = Path(metadata_path)
        self.metadata_path.parent.mkdir(exist_ok=True)
        if not self.metadata_path.exists():
            self.metadata_path.write_text(json.dumps({
                "entities": [], "relations": [], "views": []
            }, indent=2))

    def load_metadata(self):
        """Load current metadata snapshot."""
        try:
            return json.loads(self.metadata_path.read_text())
        except Exception:
            return {"entities": [], "relations": [], "views": []}

    def _paraphrase(self, requirement: str) -> str:
        """Very simple paraphrase: clean and normalize the text."""
        text = requirement.strip()
        text = re.sub(r"\s+", " ", text)
        if not text.endswith("."):
            text += "."
        return f"The system should {text[0].lower()}{text[1:]}"

    def _clarifications_needed(self, text: str):
        """Heuristics to decide what needs clarification."""
        questions = []
        if re.search(r"(customer|order|task|person)", text, re.I):
            if not re.search(r"(string|number|date|email|phone)", text, re.I):
                questions.append("Please specify key attributes and their types (e.g., name:string, created_at:date).")
        if "many" in text or "multiple" in text:
            if not re.search(r"(1:N|N:M|N:1)", text):
                questions.append("Please confirm the relation multiplicities (e.g., 1:N, N:M).")
        return questions

    def process(self, requirement: str, mode: str = "nl", clarifications_answered: dict | None = None):
        """
        Process a requirement and return a summary with possible clarifications.
        clarifications_answered: optional dict of answers from the user to merge.
        """
        summary = self._paraphrase(requirement)
        clarifications = self._clarifications_needed(requirement)

        # If user already answered clarifications, merge into summary
        if clarifications_answered:
            for key, answer in clarifications_answered.items():
                summary += f" {answer}"
            clarifications = []  # answered, so no pending clarifications

        status = "ok" if requirement.strip() and not clarifications else "incomplete"

        # Simulated usage (replace with real API usage if needed)
        usage = {
            "prompt_tokens": len(requirement.split()),
            "completion_tokens": len(summary.split())
        }

        return {
            "status": status,
            "mode": mode,
            "text": summary,
            "clarifications": clarifications,
            "usage": usage
        }
