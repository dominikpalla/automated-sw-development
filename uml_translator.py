# uml_translator.py
import re


class UMLTranslator:
    """
    UMLTranslator converts clarified natural language requirements
    into a UML-enriched JSON specification.
    - Adds ui_hints for form generation (e.g., <select> for foreign keys).
    - No diagrams rendered; JSON only.
    """

    def translate(self, clarified_text: str):
        text = clarified_text.lower()
        entities, relations, views, clarifications = [], [], [], []

        # --- Example heuristics (extendable with AI if needed) ---
        if "customer" in text:
            entities.append({
                "name": "Customer",
                "attributes": [
                    {"name": "id", "type": "int", "required": True},
                    {"name": "name", "type": "string", "required": True}
                ],
                "operations": [],
                "ui_hints": {}
            })

        if "car" in text:
            ent = {
                "name": "Car",
                "attributes": [
                    {"name": "id", "type": "int", "required": True},
                    {"name": "make", "type": "string", "required": True},
                    {"name": "model", "type": "string", "required": True},
                ],
                "operations": [],
                "ui_hints": {}
            }
            entities.append(ent)

        # --- Relation detection ---
        if "customer" in text and "car" in text:
            relations.append({
                "from": "Customer",
                "to": "Car",
                "relation_type": "association",
                "multiplicity_from": "1",
                "multiplicity_to": "N",
                "role_from": None,
                "role_to": None
            })

            # Add foreign key to Car
            for e in entities:
                if e["name"] == "Car":
                    e["attributes"].append(
                        {"name": "customer_id", "type": "int", "required": True}
                    )
                    e["ui_hints"] = {
                        "select_fields": [
                            {
                                "attribute": "customer_id",
                                "target_entity": "Customer",
                                "label_attr": "name"
                            }
                        ]
                    }

        if not entities:
            clarifications.append("No entities were detected. Please specify entities, attributes, and relations.")

        uml_json = {
            "entities": entities,
            "relations": relations,
            "views": views,
            "uml": {"sequence": []}
        }

        usage = {
            "prompt_tokens": len(clarified_text.split()),
            "completion_tokens": len(str(uml_json).split())
        }

        return {
            "status": "ok" if entities else "incomplete",
            "json": uml_json,
            "clarifications": clarifications,
            "usage": usage
        }
