# feedback.py
import json


class FeedbackEngine:
    """
    FeedbackEngine decides how to handle validation issues:
    - auto_fixed: trivial issues can be patched automatically.
    - needs_repair: constructs a repair prompt for CodeGen.
    - needs_clarification: cannot resolve, must ask user.
    - ok: no issues.
    """

    def process(self, validation_report: dict, artefacts: dict, spec: dict | None):
        if not validation_report or validation_report.get("status") == "pass":
            return {"status": "ok", "repairs": {}, "questions": []}

        repairs, questions = {}, []
        repair_prompt = None

        for entry in validation_report.get("issues", []):
            fname = entry.get("file")
            for issue in entry.get("issues", []):
                issue_lower = issue.lower()

                # --- Auto-fix: trivial syntax or formatting ---
                if "syntaxerror" in issue_lower and fname and fname.endswith(".py"):
                    # Example trivial fix: ensure newline at end
                    repaired = artefacts.get(fname, "")
                    if not repaired.endswith("\n"):
                        repaired += "\n"
                    repairs[fname] = repaired

                # --- Needs repair: AI or semantic mismatch ---
                elif "missing" in issue_lower or "incorrect" in issue_lower \
                     or "not implemented" in issue_lower or "aivalidator" in fname.lower():
                    repair_prompt = self._build_repair_prompt(issue, artefacts, spec)

                # --- Needs clarification: requirement unclear ---
                elif "ambiguous" in issue_lower or "unclear" in issue_lower:
                    questions.append(f"Clarification needed: {issue}")

        # Decide outcome
        if repairs:
            return {"status": "auto_fixed", "repairs": repairs, "questions": []}

        if repair_prompt:
            return {
                "status": "needs_repair",
                "repair_prompt": repair_prompt,
                "artefacts": artefacts
            }

        if questions:
            return {"status": "needs_clarification", "repairs": {}, "questions": questions}

        return {"status": "ok", "repairs": {}, "questions": []}

    def _build_repair_prompt(self, issue: str, artefacts: dict, spec: dict | None):
        """
        Construct a repair prompt for CodeGen using the original code,
        the detected issue, and optionally the UML/requirement spec.
        """
        prompt = f"""
        The following generated code does not fully satisfy the requirement.

        Issue detected:
        {issue}

        Current artefacts:
        {json.dumps(artefacts, indent=2)}

        """
        if spec:
            prompt += f"""
            Requirement specification (UML/JSON):
            {json.dumps(spec, indent=2)}
            """

        prompt += """
        Please fix the code to resolve the issue while keeping
        the rest of the implementation intact.
        """

        return prompt.strip()
