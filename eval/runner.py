"""
Eval runner — drives (adapter, task, dataset) into a results JSONL.

Design notes:
- One row per (adapter.model_id, task.name, item_id, sample_idx).
- Header row (first line, `_meta: true`) carries reproducibility metadata:
  model_id, dataset hash, harness git SHA, host, timestamp, held-out flag.
- Resumable: re-running skips items already in the output file (matched by
  item_id + sample_idx). On resume the existing header is validated against
  the current run's identity (model_id, task, dataset hash, n_samples,
  held-out) and the runner REFUSES to append on mismatch — so an output file
  can't silently accumulate rows from two different (model, task, dataset).
- Reliability is layered. Transient adapter failures (network errors, timeouts,
  429/5xx — see _is_transient) are retried in-process with exponential backoff,
  tunable via max_attempts/backoff_base on run(). A permanent failure, or a
  transient one that exhausts its retries, writes a row with an `error` field
  (annotated with `attempts` + `error_classification`) rather than halting, and
  is left un-`done` so the next resume run re-attempts it. In short: in-process
  retry absorbs blips; resume absorbs anything that outlives the process.
- Held-out discipline (spec §5): a held-out dataset can only be run with
  include_held_out=True, and is verified against a committed SHA-256 manifest
  (`data/holdout.sha256`, produced by scripts/lock_holdout.py) before any
  scoring. This makes the methodology's held-out lock enforceable, not just
  documented.

All metrics are computed downstream from the JSONL — re-running scoring
NEVER requires re-running the model.

CLI: `python -m eval.runner --task A --dataset data/dev/set1.jsonl --output
results/out.jsonl --adapter mock`. Held-out sets require --include-held-out.
"""

import argparse
import hashlib
import json
import socket
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

from adapters.base import ModelAdapter
from tasks.base import Task


class HeldOutAccessError(RuntimeError):
    """Raised when a held-out set is run without explicit opt-in."""


class HoldoutLockError(RuntimeError):
    """Raised when a held-out set is missing its lock manifest or doesn't match it."""


class ResumeHeaderMismatch(RuntimeError):
    """Raised when resuming into an output file whose header identity differs."""


# Header fields that define a run's identity. host/started_at/git SHA legitimately
# vary across resume invocations, so they are NOT part of the resume check.
_RESUME_IDENTITY_KEYS = (
    "model_id", "task", "dataset_sha256_prefix", "n_samples", "held_out",
)


# HTTP statuses worth retrying: request-timeout / conflict / too-early /
# rate-limit, plus the 5xx server-side failures. Every other status (notably
# 4xx like 400/401/403/404) is a permanent client error we must not hammer.
_RETRYABLE_HTTP_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


def _is_transient(exc: BaseException) -> bool:
    """Classify an adapter exception as transient (worth an in-process retry)
    vs permanent (record and move on).

    urllib.error.HTTPError is checked FIRST because it subclasses URLError: a
    401/403/404 is a permanent client error even though isinstance(exc, URLError)
    is True for it. Only the retryable statuses above are transient. Connection-
    level failures (URLError without a status, timeouts, refused connections) are
    always transient; anything else — including a deterministic parse/score bug
    surfacing from task code — is permanent and must not be retried.

    Note: socket.timeout is listed alongside TimeoutError because it is only an
    alias for it on Python 3.10+, and this harness supports 3.9 (pyproject)."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in _RETRYABLE_HTTP_STATUS
    return isinstance(exc, (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError))


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


def _canonical_bytes(item: dict) -> bytes:
    """Stable canonical serialization of one dataset item. The single source of
    truth for both fallback item IDs and held-out set hashing — scripts that
    lock a held-out set import this so their hashes always agree with the runner."""
    return json.dumps(item, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _stable_item_id(item: dict) -> str:
    """Reproducible fallback ID for items lacking `id`/`article_id`.

    Uses SHA-256, NOT the builtin hash() — hash() is salted per process
    (PYTHONHASHSEED), so it would produce a different ID every run and break
    the reproducibility the whole harness is built on."""
    return hashlib.sha256(_canonical_bytes(item)).hexdigest()[:16]


def _holdout_aggregate(items: list) -> str:
    """Order-independent SHA-256 over a set of items. Reordering the file does
    not change this — what we lock is set membership, not line order."""
    per_item = sorted(hashlib.sha256(_canonical_bytes(it)).hexdigest() for it in items)
    return hashlib.sha256("\n".join(per_item).encode("utf-8")).hexdigest()


def _is_holdout(path: Path) -> bool:
    """Heuristic split detection matching the `data/holdout/` convention
    (spec §5): held-out if any path component is `holdout`, or the filename
    stem contains `holdout` (covers the tracked `sample_holdout.jsonl` fixture)."""
    if any(part.lower() == "holdout" for part in path.parts):
        return True
    return "holdout" in path.stem.lower()


def _verify_holdout(items: list, manifest_path: Path) -> str:
    """Verify `items` against a committed lock manifest. Returns the verified
    aggregate hash. Raises HoldoutLockError if the manifest is missing or the
    set has changed since it was locked."""
    if not manifest_path.exists():
        raise HoldoutLockError(
            f"held-out run requires a lock manifest at {manifest_path}, but none "
            f"exists. Lock the set first: python scripts/lock_holdout.py "
            f"--dataset <path> --out {manifest_path}"
        )
    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        raise HoldoutLockError(f"could not read lock manifest {manifest_path}: {e}") from e

    actual = _holdout_aggregate(items)
    expected = manifest.get("aggregate_sha256")
    if expected != actual:
        raise HoldoutLockError(
            f"held-out set does not match its lock manifest {manifest_path}: "
            f"expected aggregate {expected}, got {actual} ({len(items)} items vs "
            f"locked {manifest.get('n_items')}). The held-out set changed after "
            f"locking — refusing to score against a mutated test set."
        )
    return actual


def _header_row(adapter: ModelAdapter, task: Task, dataset_path: Path,
                n_samples: int, repo_root: Path, held_out: bool = False,
                holdout_aggregate_sha256: str = None) -> dict:
    return {
        "_meta": True,
        "model_id": adapter.model_id,
        "task": task.name,
        "dataset_path": str(dataset_path),
        "dataset_sha256_prefix": _dataset_hash(dataset_path),
        "n_samples": n_samples,
        "held_out": held_out,
        "holdout_aggregate_sha256": holdout_aggregate_sha256,
        "harness_git_sha": _git_sha(repo_root),
        "host": socket.gethostname(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _read_header(output_path: Path) -> dict:
    """Return the existing `_meta` header row, or {} if none."""
    with output_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                return {}
            return row if row.get("_meta") else {}
    return {}


def _validate_resume_header(output_path: Path, new_header: dict) -> None:
    """Refuse to append if the existing header's run identity differs from the
    current run — prevents an output file from mixing models/tasks/datasets."""
    existing = _read_header(output_path)
    if not existing:
        return  # no header to validate against (empty/legacy file)
    mismatches = {
        k: {"existing": existing.get(k), "current": new_header.get(k)}
        for k in _RESUME_IDENTITY_KEYS
        if existing.get(k) != new_header.get(k)
    }
    if mismatches:
        raise ResumeHeaderMismatch(
            f"refusing to resume into {output_path}: run identity differs from the "
            f"existing header {mismatches}. Use a fresh output file per "
            f"(model, task, dataset)."
        )


def _load_existing(output_path: Path) -> set:
    """Scan existing output and return (item_id, sample_idx) keys already
    completed successfully — used for resume. Error rows are NOT marked
    complete; they get retried on resume. Safe to key on (item_id, sample_idx)
    alone because _validate_resume_header guarantees the file belongs to this
    exact (model, task, dataset) run."""
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
        output_path: Path, n_samples: int = 1, repo_root: Path = None,
        include_held_out: bool = False, split: str = "auto",
        holdout_manifest: Path = None,
        max_attempts: int = 3, backoff_base: float = 0.5) -> dict:
    """Execute one (adapter, task, dataset) run. Returns summary stats.

    split: "auto" detects held-out by path (see _is_holdout); "dev"/"holdout"
    force it. A held-out run requires include_held_out=True and a matching lock
    manifest (default data/holdout.sha256 under repo_root).

    max_attempts: total attempts per item including the first (1 disables retry).
    backoff_base: exponential backoff seconds — between attempt N (0-based) and
    the next, the runner sleeps backoff_base * 2**N. Only transient failures
    (see _is_transient) are retried; permanent ones are recorded immediately."""
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")
    if backoff_base < 0:
        raise ValueError(f"backoff_base must be >= 0, got {backoff_base}")
    dataset_path = Path(dataset_path)
    output_path = Path(output_path)
    repo_root = Path(repo_root) if repo_root else dataset_path.parent

    if split == "auto":
        held_out = _is_holdout(dataset_path)
    elif split in ("dev", "holdout"):
        held_out = (split == "holdout")
    else:
        raise ValueError(f"split must be 'auto', 'dev', or 'holdout', got {split!r}")

    items = _load_dataset(dataset_path)

    verified_sha = None
    if held_out:
        if not include_held_out:
            raise HeldOutAccessError(
                f"{dataset_path} is a held-out set. Refusing to run without "
                f"include_held_out=True (CLI: --include-held-out). Held-out data "
                f"is for final scoring only — never prompt iteration."
            )
        manifest_path = Path(holdout_manifest) if holdout_manifest else (
            repo_root / "data" / "holdout.sha256")
        verified_sha = _verify_holdout(items, manifest_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = _header_row(adapter, task, dataset_path, n_samples, repo_root,
                         held_out=held_out, holdout_aggregate_sha256=verified_sha)

    is_new = (not output_path.exists()) or output_path.stat().st_size == 0
    if not is_new:
        _validate_resume_header(output_path, header)
    existing = _load_existing(output_path)

    n_new = 0
    n_skip = 0
    n_error = 0
    n_retries = 0

    with output_path.open("a") as out:
        if is_new:
            out.write(json.dumps(header) + "\n")
            out.flush()

        for item in items:
            item_id = item.get("id") or item.get("article_id") or _stable_item_id(item)
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
                for attempt in range(max_attempts):
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
                        break
                    except Exception as e:
                        transient = _is_transient(e)
                        if transient and attempt < max_attempts - 1:
                            time.sleep(backoff_base * 2 ** attempt)
                            n_retries += 1
                            continue
                        # Permanent, or transient with no attempts left: record
                        # the failure (un-`done`, so resume re-attempts it) with
                        # enough provenance to tell "gave up after N" from "never
                        # retried".
                        row["error"] = f"{type(e).__name__}: {e}"
                        row["attempts"] = attempt + 1
                        row["error_classification"] = "transient" if transient else "permanent"
                        n_error += 1
                        break
                out.write(json.dumps(row) + "\n")
                out.flush()

    return {
        "completed": n_new,
        "skipped_resume": n_skip,
        "errors": n_error,
        "transient_retries": n_retries,
        "held_out": held_out,
        "output": str(output_path),
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _build_adapter(args):
    if args.adapter == "mock":
        from adapters.mock import MockAdapter
        responses = json.loads(Path(args.mock_responses).read_text()) if args.mock_responses else {}
        return MockAdapter(responses, model_id=args.model_id or "mock-v1")
    if args.adapter == "anthropic":
        from adapters.anthropic import AnthropicAdapter
        return AnthropicAdapter(_require(args.model_id, "--model-id"))
    if args.adapter == "openai":
        from adapters.openai import OpenAIAdapter
        return OpenAIAdapter(_require(args.model_id, "--model-id"))
    if args.adapter == "ollama":
        from adapters.ollama import OllamaAdapter
        return OllamaAdapter(
            _require(args.model_id, "--model-id"),
            _require(args.hf_sha, "--hf-sha"),
            host=args.ollama_host,
        )
    raise ValueError(f"unknown adapter {args.adapter!r}")


def _build_task(name: str):
    from tasks import categorization, summarization
    registry = {
        "A": categorization.task, "categorization": categorization.task,
        "B": summarization.task, "summarization": summarization.task,
    }
    if name not in registry:
        raise ValueError(f"unknown task {name!r}; choose from {sorted(registry)}")
    return registry[name]


def _require(value, flag: str):
    if not value:
        raise SystemExit(f"{flag} is required for this adapter")
    return value


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m eval.runner",
        description="Run one (adapter, task, dataset) eval into a results JSONL.",
    )
    p.add_argument("--task", required=True, help="A|categorization|B|summarization")
    p.add_argument("--dataset", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--adapter", default="mock",
                   choices=["mock", "anthropic", "openai", "ollama"])
    p.add_argument("--model-id", default=None,
                   help="model snapshot id (e.g. claude-sonnet-4-6-20260101)")
    p.add_argument("--hf-sha", default=None, help="HF SHA for ollama model pinning")
    p.add_argument("--ollama-host", default="http://localhost:11434",
                   help="base URL of the Ollama server (ollama adapter only; "
                        "e.g. http://dgx-spark.local:11434 to drive a remote box "
                        "while the harness runs elsewhere). Ignored by other adapters.")
    p.add_argument("--mock-responses", default=None,
                   help="JSON file mapping prompt-substring -> response (mock adapter)")
    p.add_argument("--n-samples", type=int, default=1)
    p.add_argument("--max-attempts", type=int, default=3,
                   help="total attempts per item incl. the first try (1 disables retry)")
    p.add_argument("--backoff-base", type=float, default=0.5,
                   help="exponential backoff seconds: sleep = base * 2**attempt (0 = no wait)")
    p.add_argument("--split", default="auto", choices=["auto", "dev", "holdout"])
    p.add_argument("--include-held-out", action="store_true", default=False,
                   help="REQUIRED to run against a held-out set (off by default).")
    p.add_argument("--holdout-manifest", default=None, type=Path,
                   help="lock manifest path (default: data/holdout.sha256)")
    p.add_argument("--repo-root", default=None, type=Path)
    return p


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)

    repo_root = args.repo_root or Path(__file__).resolve().parent.parent
    try:
        summary = run(
            _build_adapter(args), _build_task(args.task), args.dataset, args.output,
            n_samples=args.n_samples, repo_root=repo_root,
            include_held_out=args.include_held_out, split=args.split,
            holdout_manifest=args.holdout_manifest,
            max_attempts=args.max_attempts, backoff_base=args.backoff_base,
        )
    except (HeldOutAccessError, HoldoutLockError, ResumeHeaderMismatch, ValueError) as e:
        # Expected guardrail trips / bad inputs (unknown task, bad --max-attempts) —
        # report cleanly, no traceback.
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
