"""
Eval runner — drives (adapter, task, dataset) into a results JSONL.

Design notes:
- One row per (adapter.model_id, task.name, item_id, sample_idx).
- Header row (first line, `_meta: true`) carries reproducibility metadata:
  model_id, dataset hash, harness git SHA, host, timestamp.
- Resumable: re-running skips items already in the output file (matched by
  item_id + sample_idx). Header row preserved across resumes.
- Failures (API errors, parse exceptions) write a row with an `error` field
  rather than halting — keeps multi-hour runs robust.

All metrics are computed downstream from the JSONL — re-running scoring
NEVER requires re-running the model.
"""

import hashlib
import json
import socket
import subprocess
import time
from pathlib import Path

from adapters.base import ModelAdapter
from tasks.base import Task


def _git_sha(repo_root: Path) -> str:
    """Best-effort: return current git SHA, or 'no-git' if unavailable."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        return result.stdout.strip() if result.returncode == 0 else "no-git"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "no-git"


def _dataset_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _header_row(adapter: ModelAdapter, task: Task, dataset_path: Path,
                n_samples: int, repo_root: Path) -> dict:
    return {
        "_meta": True,
        "model_id": adapter.model_id,
        "task": task.name,
        "dataset_path": str(dataset_path),
        "dataset_sha256_prefix": _dataset_hash(dataset_path),
        "n_samples": n_samples,
        "harness_git_sha": _git_sha(repo_root),
        "host": socket.gethostname(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _load_existing(output_path: Path) -> set:
    """Scan existing output and return (item_id, sample_idx) keys already
    completed successfully — used for resume. Error rows are NOT marked
    complete; they get retried on resume."""
    done = set()
    if not output_path.exists():
        return done
    with output_path.open() as f:
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("_meta"):
                continue
            if "item_id" in row and "sample_idx" in row and "error" not in row:
                done.add((row["item_id"], row["sample_idx"]))
    return done


def _load_dataset(path: Path) -> list:
    items = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def run(adapter: ModelAdapter, task: Task, dataset_path: Path,
        output_path: Path, n_samples: int = 1, repo_root: Path = None) -> dict:
    """Execute one (adapter, task, dataset) run. Returns summary stats."""
    repo_root = repo_root or dataset_path.parent
    items = _load_dataset(dataset_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    existing = _load_existing(output_path)
    is_new = (not output_path.exists()) or output_path.stat().st_size == 0

    n_new = 0
    n_skip = 0
    n_error = 0

    with output_path.open("a") as out:
        if is_new:
            out.write(json.dumps(_header_row(
                adapter, task, dataset_path, n_samples, repo_root)) + "\n")
            out.flush()

        for item in items:
            item_id = item.get("id") or item.get("article_id") or str(hash(json.dumps(item, sort_keys=True)))
            for s in range(n_samples):
                if (item_id, s) in existing:
                    n_skip += 1
                    continue
                row = {
                    "model_id": adapter.model_id,
                    "task": task.name,
                    "item_id": item_id,
                    "sample_idx": s,
                }
                prompt = task.prompt_template(item)
                try:
                    completion = adapter.complete(prompt, task.sampling_params)
                    parsed = task.parse_output(completion.text)
                    scored = task.score(parsed, item)
                    row.update({
                        "raw_output": completion.text,
                        "input_tokens": completion.input_tokens,
                        "output_tokens": completion.output_tokens,
                        "latency_ms": completion.latency_ms,
                        "score": scored,
                    })
                    n_new += 1
                except Exception as e:
                    row["error"] = f"{type(e).__name__}: {e}"
                    n_error += 1
                out.write(json.dumps(row) + "\n")
                out.flush()

    return {
        "completed": n_new,
        "skipped_resume": n_skip,
        "errors": n_error,
        "output": str(output_path),
    }
