# manager.py — Flask web app (Manager cycle with clarifications and repairs)

from flask import Flask, request, jsonify, render_template
from pathlib import Path
from dotenv import load_dotenv
import os, json, time, uuid

# specialized modules
from interpreter import Interpreter
from uml_translator import UMLTranslator
from cogen import CodeGen
from validation import Validator
from feedback import FeedbackEngine
from progress_logger import ProgressLogger


# -------------------------
# Setup
# -------------------------
load_dotenv()
app = Flask(__name__, template_folder="templates", static_folder="static")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
METADATA_PATH = DATA_DIR / "metadata.json"
LOG_PATH = DATA_DIR / "progress_log.json"
MODULES_DIR = Path("modules")
MODULES_DIR.mkdir(exist_ok=True)

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4.1")

logger = ProgressLogger(LOG_PATH, model=MODEL_NAME)
interpreter = Interpreter(METADATA_PATH)
uml_translator = UMLTranslator()
codegen = CodeGen(METADATA_PATH, MODULES_DIR)
validator = Validator()
feedback_engine = FeedbackEngine()


# --------------------------------------
# Manager cycle
# --------------------------------------
def run_cycle(
    requirement: str,
    mode: str = "nl",
    clarifications_answered: dict | None = None,
    max_iters: int = 3,
):
    start = time.time()
    iterations, clarifications = 0, 0
    artefacts, spec, report, last_validation = {}, None, None, None
    status = "fail"
    run_id = str(uuid.uuid4())

    tokens_in, tokens_out = 0, 0

    # Interpret step
    inter = interpreter.process(requirement, mode, clarifications_answered)
    _ti, _to = _usage_from(inter)
    tokens_in += _ti
    tokens_out += _to

    if inter.get("status") == "incomplete":
        clarifications += 1
        return _metrics(
            "clarification",
            iterations,
            clarifications,
            start,
            mode,
            run_id,
            last_validation,
            tokens_in,
            tokens_out,
            extra={"clarifications": inter.get("clarifications", [])},
        )

    # UML path
    if mode == "uml":
        uml_out = uml_translator.translate(inter.get("text", ""))
        _ti, _to = _usage_from(uml_out)
        tokens_in += _ti
        tokens_out += _to
        spec = uml_out.get("json")
        payload_for_codegen = {"mode": "uml", "json": spec}
    else:
        payload_for_codegen = {"mode": "nl", "text": inter.get("text", "")}

    # Generation → Validation → Feedback loop
    while iterations < max_iters:
        iterations += 1
        gen_out = codegen.generate(payload_for_codegen)
        _ti, _to = _usage_from(gen_out)
        tokens_in += _ti
        tokens_out += _to

        artefacts = gen_out.get("artefacts", {})
        report = gen_out.get("report", {})
        if gen_out.get("status") == "needs_clarification":
            clarifications += 1
            status = "clarification"
            break

        val_out = validator.validate(
            artefacts, report, requirement=requirement, mode=mode
        )
        _ti, _to = _usage_from(val_out)
        tokens_in += _ti
        tokens_out += _to
        last_validation = val_out
        if val_out.get("status") == "pass":
            status = "pass"
            break

        fb_out = feedback_engine.process(val_out, artefacts, spec)

        if fb_out.get("status") == "needs_repair":
            # Send artefacts + repair_prompt back to CodeGen
            payload_for_codegen["repair_prompt"] = fb_out["repair_prompt"]
            payload_for_codegen["artefacts"] = artefacts
            continue
        elif fb_out.get("status") == "auto_fixed":
            for fname, content in fb_out.get("repairs", {}).items():
                artefacts[fname] = content
            continue
        elif fb_out.get("status") == "needs_clarification":
            clarifications += 1
            status = "clarification"
            break

    return _metrics(
        status,
        iterations,
        clarifications,
        start,
        mode,
        run_id,
        last_validation,
        tokens_in,
        tokens_out,
    )


def _usage_from(obj: dict):
    if not isinstance(obj, dict):
        return 0, 0
    if "usage" in obj and isinstance(obj["usage"], dict):
        return (
            int(obj["usage"].get("prompt_tokens", 0)),
            int(obj["usage"].get("completion_tokens", 0)),
        )
    if "tokens_input" in obj or "tokens_output" in obj:
        return (
            int(obj.get("tokens_input", 0) or 0),
            int(obj.get("tokens_output", 0) or 0),
        )
    return 0, 0


def _metrics(
    status,
    iterations,
    clarifications,
    start,
    mode,
    run_id,
    last_validation=None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    extra: dict | None = None,
):
    duration = time.time() - start
    metrics = {
        "iterations": iterations,
        "issues_count": len(last_validation.get("issues", []))
        if last_validation
        else 0,
        "clarifications_count": clarifications,
        "duration_sec": round(duration, 3),
        "mode": mode,
        "pass_fail": status,
        "run_id": run_id,
    }
    log_obj = {"event": "run", "metrics": metrics}
    if extra:
        log_obj.update(extra)

    logger.log(
        log_obj, tokens_input=tokens_in, tokens_output=tokens_out
    )
    out = {"status": status, "metrics": metrics, "log_ref": str(logger.path)}
    if extra:
        out.update(extra)
    return out


# -------------------------
# View routes
# -------------------------
@app.get("/")
def index_view():
    return render_template("index.html")


@app.get("/entities")
def entities_view():
    meta = interpreter.load_metadata()
    return render_template("entities.html", metadata=meta)


@app.get("/logs")
def logs_view():
    logs = []
    try:
        with LOG_PATH.open() as f:
            for line in f:
                logs.append(json.loads(line))
    except Exception:
        pass
    return render_template("logs.html", logs=logs)


@app.get("/health")
def health_view():
    return jsonify({"ok": True, "model": MODEL_NAME})


# -------------------------
# API routes
# -------------------------
@app.post("/run")
def run_endpoint():
    payload = request.get_json(force=True)
    requirement = payload.get("requirement", "")
    mode = payload.get("mode", "nl")
    clarifications_answered = payload.get("clarifications_answered")
    out = run_cycle(
        requirement=requirement,
        mode=mode,
        clarifications_answered=clarifications_answered,
    )
    return jsonify(out)


@app.get("/state")
def state_endpoint():
    meta = interpreter.load_metadata()
    return jsonify(meta)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
