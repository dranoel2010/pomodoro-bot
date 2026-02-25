#!/usr/bin/env python3
"""Benchmark llama.cpp model/quantization throughput on Raspberry Pi 5."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llama_cpp import Llama


DEFAULT_PROMPT = "Starte einen Pomodoro fuer 25 Minuten zum Thema Code Review."


@dataclass(frozen=True, slots=True)
class RunSample:
    duration_seconds: float
    completion_tokens: int | None
    finish_reason: str | None

    @property
    def completion_tokens_per_second(self) -> float | None:
        if not self.completion_tokens or self.duration_seconds <= 0:
            return None
        return self.completion_tokens / self.duration_seconds


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    model_path: str
    n_threads: int
    n_threads_batch: int
    n_ctx: int
    n_batch: int
    n_ubatch: int | None
    median_duration_seconds: float
    median_tokens_per_second: float
    median_completion_tokens: int
    finish_reasons: dict[str, int]


def _parse_csv_ints(raw: str) -> list[int]:
    values: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        values.append(int(token))
    if not values:
        raise ValueError("At least one integer value is required")
    return values


def _extract_completion_tokens(response: dict[str, Any]) -> int | None:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return None

    completion = usage.get("completion_tokens")
    if isinstance(completion, int):
        return completion

    prompt = usage.get("prompt_tokens")
    total = usage.get("total_tokens")
    if isinstance(prompt, int) and isinstance(total, int):
        derived = total - prompt
        return derived if derived >= 0 else None
    return None


def _run_one(
    *,
    llm: Llama,
    prompt: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
    top_k: int,
    min_p: float,
    repeat_penalty: float,
) -> RunSample:
    started_at = time.perf_counter()
    response = llm.create_chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "Du bist ein deutscher Assistent. "
                    "Antworte knapp und nur als JSON mit assistant_text und tool_call."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        min_p=min_p,
        repeat_penalty=repeat_penalty,
    )
    duration_seconds = time.perf_counter() - started_at

    finish_reason = None
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            raw_finish = first_choice.get("finish_reason")
            if raw_finish is not None:
                finish_reason = str(raw_finish)

    return RunSample(
        duration_seconds=duration_seconds,
        completion_tokens=_extract_completion_tokens(response),
        finish_reason=finish_reason,
    )


def _benchmark_case(
    *,
    model_path: str,
    prompt: str,
    warmup_runs: int,
    measured_runs: int,
    n_threads: int,
    n_threads_batch: int,
    n_ctx: int,
    n_batch: int,
    n_ubatch: int | None,
    max_tokens: int,
    temperature: float,
    top_p: float,
    top_k: int,
    min_p: float,
    repeat_penalty: float,
    use_mmap: bool,
    use_mlock: bool,
) -> BenchmarkResult:
    llm = Llama(
        model_path=model_path,
        n_threads=n_threads,
        n_threads_batch=n_threads_batch,
        n_ctx=n_ctx,
        n_batch=n_batch,
        n_ubatch=n_ubatch,
        use_mmap=use_mmap,
        use_mlock=use_mlock,
        verbose=False,
    )

    for _ in range(warmup_runs):
        _run_one(
            llm=llm,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            repeat_penalty=repeat_penalty,
        )

    samples: list[RunSample] = []
    for _ in range(measured_runs):
        sample = _run_one(
            llm=llm,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            repeat_penalty=repeat_penalty,
        )
        samples.append(sample)

    finish_reasons: dict[str, int] = {}
    for sample in samples:
        label = sample.finish_reason or "unknown"
        finish_reasons[label] = finish_reasons.get(label, 0) + 1

    durations = [sample.duration_seconds for sample in samples]
    completion_tokens = [sample.completion_tokens or 0 for sample in samples]
    tokens_per_second = [
        sample.completion_tokens_per_second
        for sample in samples
        if sample.completion_tokens_per_second is not None
    ]

    median_tokens_per_second = (
        statistics.median(tokens_per_second) if tokens_per_second else 0.0
    )

    return BenchmarkResult(
        model_path=model_path,
        n_threads=n_threads,
        n_threads_batch=n_threads_batch,
        n_ctx=n_ctx,
        n_batch=n_batch,
        n_ubatch=n_ubatch,
        median_duration_seconds=statistics.median(durations),
        median_tokens_per_second=median_tokens_per_second,
        median_completion_tokens=int(statistics.median(completion_tokens)),
        finish_reasons=finish_reasons,
    )


def _print_ranked(results: list[BenchmarkResult]) -> None:
    ranked = sorted(
        results,
        key=lambda item: (item.median_tokens_per_second, -item.median_duration_seconds),
        reverse=True,
    )

    print("\nRanked throughput results (higher tokens/sec is better):")
    print(
        "rank | model | n_threads | n_threads_batch | med_tps | med_latency_ms | med_completion_toks | finishes"
    )
    print("-" * 130)
    for index, result in enumerate(ranked, start=1):
        print(
            f"{index:>4} | "
            f"{Path(result.model_path).name} | "
            f"{result.n_threads:>9} | "
            f"{result.n_threads_batch:>15} | "
            f"{result.median_tokens_per_second:>7.2f} | "
            f"{round(result.median_duration_seconds * 1000):>14} | "
            f"{result.median_completion_tokens:>19} | "
            f"{result.finish_reasons}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pi 5 llama.cpp model/quantization throughput sweep"
    )
    parser.add_argument(
        "--models",
        nargs="+",
        required=True,
        help="One or more GGUF model paths to benchmark.",
    )
    parser.add_argument(
        "--threads",
        default="2,3,4",
        help="Comma-separated n_threads values (default: 2,3,4).",
    )
    parser.add_argument(
        "--threads-batch",
        default="",
        help="Comma-separated n_threads_batch values. Defaults to --threads.",
    )
    parser.add_argument("--n-ctx", type=int, default=2048)
    parser.add_argument("--n-batch", type=int, default=256)
    parser.add_argument("--n-ubatch", type=int, default=128)
    parser.add_argument("--max-tokens", type=int, default=192)
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--prompt-file", default="")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--min-p", type=float, default=0.05)
    parser.add_argument("--repeat-penalty", type=float, default=1.1)
    parser.add_argument("--use-mmap", action="store_true", default=True)
    parser.add_argument("--no-use-mmap", dest="use_mmap", action="store_false")
    parser.add_argument("--use-mlock", action="store_true", default=False)
    parser.add_argument("--json-out", default="")

    args = parser.parse_args()

    prompt = args.prompt
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8").strip()

    thread_values = _parse_csv_ints(args.threads)
    thread_batch_values = (
        _parse_csv_ints(args.threads_batch)
        if args.threads_batch.strip()
        else thread_values
    )

    results: list[BenchmarkResult] = []
    for model in args.models:
        model_path = str(Path(model).expanduser().resolve())
        if not Path(model_path).is_file():
            raise FileNotFoundError(f"Model not found: {model_path}")

        for n_threads in thread_values:
            for n_threads_batch in thread_batch_values:
                print(
                    "Running benchmark:",
                    Path(model_path).name,
                    f"n_threads={n_threads}",
                    f"n_threads_batch={n_threads_batch}",
                )
                result = _benchmark_case(
                    model_path=model_path,
                    prompt=prompt,
                    warmup_runs=args.warmup_runs,
                    measured_runs=args.runs,
                    n_threads=n_threads,
                    n_threads_batch=n_threads_batch,
                    n_ctx=args.n_ctx,
                    n_batch=args.n_batch,
                    n_ubatch=args.n_ubatch,
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                    top_p=args.top_p,
                    top_k=args.top_k,
                    min_p=args.min_p,
                    repeat_penalty=args.repeat_penalty,
                    use_mmap=args.use_mmap,
                    use_mlock=args.use_mlock,
                )
                results.append(result)

    _print_ranked(results)

    if args.json_out:
        payload = [
            {
                "model_path": result.model_path,
                "n_threads": result.n_threads,
                "n_threads_batch": result.n_threads_batch,
                "n_ctx": result.n_ctx,
                "n_batch": result.n_batch,
                "n_ubatch": result.n_ubatch,
                "median_duration_seconds": result.median_duration_seconds,
                "median_tokens_per_second": result.median_tokens_per_second,
                "median_completion_tokens": result.median_completion_tokens,
                "finish_reasons": result.finish_reasons,
            }
            for result in results
        ]
        output_path = Path(args.json_out)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote benchmark JSON: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
