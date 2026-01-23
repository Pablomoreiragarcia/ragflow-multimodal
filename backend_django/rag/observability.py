import time

def normalize_usage(usage: dict | None) -> tuple[int | None, int | None, int | None]:
    if not usage:
        return None, None, None

    prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
    completion = usage.get("completion_tokens", usage.get("output_tokens"))
    total = usage.get("total_tokens")

    # si total no viene pero sí prompt+completion
    if total is None and (prompt is not None or completion is not None):
        try:
            total = int(prompt or 0) + int(completion or 0)
        except Exception:
            total = None

    return (
        int(prompt) if prompt is not None else None,
        int(completion) if completion is not None else None,
        int(total) if total is not None else None,
    )

class Stopwatch:
    def __init__(self):
        self.t0 = time.perf_counter()
        self.marks = {}

    def mark(self, name: str):
        now = time.perf_counter()
        self.marks[name] = int((now - self.t0) * 1000)

    def ms_since(self, start_mark: str, end_mark: str) -> int:
        return max(0, self.marks.get(end_mark, 0) - self.marks.get(start_mark, 0))
