# progress_logger.py
from pathlib import Path
import json
import time

# price for 1k tokens (USD) – OpenAI (2025)
MODEL_PRICING = {
    "gpt-4.1": {"input": 0.005, "output": 0.015},
    "gpt-4.1-mini": {"input": 0.0005, "output": 0.0015},
    "gpt-4o": {"input": 0.0025, "output": 0.01}
}


class ProgressLogger:
    def __init__(self, path: Path, model: str = "gpt-4.1"):
        """
        path: path to the log file (JSONL)
        model: name of the model for price calculation
        """
        self.path = Path(path)
        self.path.parent.mkdir(exist_ok=True)
        if not self.path.exists():
            self.path.write_text("")
        self.model = model

    def _calc_cost(self, tokens_input: int, tokens_output: int):
        pricing = MODEL_PRICING.get(self.model, {"input": 0, "output": 0})
        cost = (tokens_input / 1000 * pricing["input"]) + \
               (tokens_output / 1000 * pricing["output"])
        return round(cost, 6)

    def log(self, obj: dict, tokens_input: int = 0, tokens_output: int = 0):
        """
        Log one run to JSONL file.
        - obj: dictionary with run data (eg. metrics)
        - tokens_input, tokens_output: number of prompt/completion tokens
        """
        entry = dict(obj)
        entry["ts"] = time.time()
        entry["tokens_input"] = tokens_input
        entry["tokens_output"] = tokens_output
        entry["cost_usd"] = self._calc_cost(tokens_input, tokens_output)
        entry["model"] = self.model

        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
