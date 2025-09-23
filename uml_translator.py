# uml_translator.py
"""
UML Translator
--------------
Takes a clarified NL requirement (from Interpreter) and produces a UML-enriched JSON specification.

Schema includes:
- entities (with attributes, datatypes, requiredness, visibility, default)
- relations (association, aggregation, composition + multiplicity)
- views (simple forms)
- optional UML sequence diagrams (messages)
"""

import os
import json
from openai import OpenAI


class UMLTranslator:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1")

    def translate(self, nl_summary: str) -> dict:
        """
        Convert clarified NL summary into UML-enriched JSON.
        Returns:
          {
            "status": "ok"|"error",
            "json": {... UML spec ...},
            "clarifications": [...],
            "usage": {prompt_tokens, completion_tokens}
          }
        """
        prompt = f"""
You are a UML specification generator.

Input requirement (clarified summary):
{nl_summary}

TASK:
Produce a JSON specification describing entities, attributes, relations, and UI hints.

Rules:
- Use this schema:
{{
  "entities": [
    {{
      "name": "EntityName",
      "attributes": [
        {{
          "name": "attr",
          "type": "string|int|float|bool|date",
          "required": true|false,
          "visibility": "public|private|protected",
          "default": null|<literal>
        }}
      ],
      "operations": []  // optional
    }}
  ],
  "relations": [
    {{
      "from": "EntityA",
      "to": "EntityB",
      "relation_type": "association|aggregation|composition",
      "multiplicity_from": "1|N|0..1|0..N",
      "multiplicity_to": "1|N|0..1|0..N",
      "role_from": null,
      "role_to": null
    }}
  ],
  "views": [
    {{
      "name": "EntityDetail",
      "entity": "EntityName",
      "elements": ["attr1","attr2"]
    }}
  ],
  "uml": {{
    "sequence": [ {{ "from":"User", "to":"System", "message":"..." }} ]
  }}
}}

- Always include "entities" and "relations" arrays (can be empty if not needed).
- Include data types for all attributes.
- Include required flags and defaults if obvious.
- Ensure multiplicities are explicitly set for all relations.
- Keep it valid JSON, no comments, no code fences.
"""

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        content = (resp.choices[0].message.content or "").strip()
        usage = {
            "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0),
            "completion_tokens": getattr(resp.usage, "completion_tokens", 0),
        }

        try:
            spec = json.loads(content)
            status = "ok"
        except Exception as e:
            spec = {}
            status = "error"

        return {
            "status": status,
            "json": spec,
            "clarifications": [],
            "usage": usage
        }
