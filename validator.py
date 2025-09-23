# validation.py
import ast
import re
import os
import json
from openai import OpenAI


class AIValidator:
    """
    AI-based validation:
    - Compares requirement vs. generated artefacts.
    - Reports if requirement is not satisfied or if there are errors.
    """

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1")

    def check(self, requirement: str, artefacts: dict, mode: str):
        """
        Ask the LLM to validate if artefacts fulfill the requirement.
        Returns (issues, usage).
        """
        prompt = f"""
        You are a strict code reviewer.

        Requirement (mode={mode}):
        {requirement}

        Generated artefacts:
        {json.dumps(artefacts, indent=2)}

        Task:
        - Check if the artefacts fully satisfy the requirement.
        - If syntax errors exist, report them.
        - If entities/attributes/relations are missing or incorrect, report them.
        - If the implementation is incorrect in any way, describe the issue.
        - If everything is correct, respond only with "OK".
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

        issues = []
        if content.lower() != "ok":
            issues.append({"file": "AIValidator", "issues": [content]})

        return issues, usage


class Validator:
    """
    Validator performs:
    - Syntax checks (Python AST).
    - Quality checks (forbidden patterns).
    - Semantic checks (required model files).
    - AI-based requirement compliance check.
    """

    def __init__(self):
        self.ai_validator = AIValidator()

    def validate(self, artefacts: dict, report: dict, requirement: str = "", mode: str = "nl"):
        issues_all = []

        # --- Syntax checks ---
        for fname, content in artefacts.items():
            if fname.endswith(".py"):
                try:
                    ast.parse(content)
                except Exception as e:
                    issues_all.append({
                        "file": fname,
                        "issues": [f"SyntaxError: {e}"]
                    })

        # --- Quality checks ---
        for fname, content in artefacts.items():
            if fname.endswith(".py"):
                if re.search(r"\beval\(|\bexec\(", content):
                    issues_all.append({
                        "file": fname,
                        "issues": ["QualityError: usage of eval/exec is forbidden."]
                    })

        # --- Semantic checks ---
        entities = report.get("entities", [])
        for ent in entities:
            expected_file = f"{ent}.model.py"
            if expected_file not in artefacts:
                issues_all.append({
                    "file": expected_file,
                    "issues": ["Missing model file for entity."]
                })

        # --- AI validation ---
        ai_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        if requirement and artefacts:
            ai_issues, ai_usage = self.ai_validator.check(requirement, artefacts, mode)
            if ai_issues:
                issues_all.extend(ai_issues)

        status = "pass" if not issues_all else "fail"

        usage = {
            "prompt_tokens": sum(len(str(a).split()) for a in artefacts.values()) + ai_usage["prompt_tokens"],
            "completion_tokens": sum(len(str(i).split()) for i in issues_all) + ai_usage["completion_tokens"]
        }

        return {
            "status": status,
            "issues": issues_all,
            "usage": usage
        }
