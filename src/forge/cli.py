"""``forge`` command line (also ``python -m forge``).

    forge benchmark validate-dataset DIR
    forge benchmark run --dataset DIR --providers FILE --target-model P [--rewriter-model P]
                        --max-model-calls N [options]
    forge benchmark verify RUN_DIR [--dataset DIR] [--database]

Datasets are versioned directories: ``benchmarks/pilot-v1`` (``forge-pilot`` 1.0.0, current)
and ``benchmarks/pilot-v0`` (0.1.0, kept unchanged so earlier runs stay verifiable). Verify
a run against the dataset version recorded in its manifest.

``run`` refuses providers that would make real model calls unless
``--allow-real-providers`` is given (real-provider runs need explicit approval), and uses
PostgreSQL only with ``--database`` (``DATABASE_URL``). Exit codes: 0 completed / valid,
1 run not completed or verification failed, 2 usage or configuration error, 130 interrupted.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from forge.benchmark.conditions import CONDITION_IDS
from forge.benchmark.dataset import SPLITS, load_dataset
from forge.errors import ForgeError
from forge.logging import configure_logging


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge")
    commands = parser.add_subparsers(dest="command", required=True)
    benchmark = commands.add_parser("benchmark", help="pilot benchmark")
    actions = benchmark.add_subparsers(dest="action", required=True)

    validate = actions.add_parser("validate-dataset", help="validate a task dataset")
    validate.add_argument("dataset", type=Path)

    run = actions.add_parser("run", help="execute a pilot run")
    run.add_argument("--dataset", type=Path, required=True)
    run.add_argument("--providers", type=Path, required=True, help="provider config JSON")
    run.add_argument("--target-model", required=True, help="model profile for the target")
    run.add_argument("--rewriter-model", help="model profile for B1 and F-legacy rewrites")
    run.add_argument("--conditions", default=",".join(CONDITION_IDS))
    run.add_argument("--split", choices=(*SPLITS, "all"), default="all")
    run.add_argument("--task", action="append", dest="tasks", help="limit to task ID(s)")
    run.add_argument("--max-model-calls", type=int, required=True)
    run.add_argument("--max-estimated-tokens", type=int)
    run.add_argument("--confirm-above-model-calls", type=int)
    run.add_argument("--confirm", action="store_true", help="confirm a run above the threshold")
    run.add_argument("--output-dir", type=Path, default=Path("benchmark-runs"))
    run.add_argument("--database", action="store_true", help="persist to DATABASE_URL")
    run.add_argument("--workspace", default="benchmarks")
    run.add_argument("--cache", action="store_true", help="use the response cache (needs DB)")
    run.add_argument("--cache-scope", help="reuse cached outputs across runs with this scope")
    run.add_argument(
        "--allow-real-providers",
        action="store_true",
        help="permit non-fake providers (real model calls; requires explicit approval)",
    )

    verify = actions.add_parser("verify", help="verify a run directory")
    verify.add_argument("run_dir", type=Path)
    verify.add_argument("--dataset", type=Path, help="recompute evaluations from this dataset")
    verify.add_argument(
        "--database", action="store_true", help="also cross-check the run row in DATABASE_URL"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    configure_logging("WARNING")
    try:
        if args.action == "validate-dataset":
            dataset = load_dataset(args.dataset)
            print(
                json.dumps(
                    {
                        "id": dataset.id,
                        "version": dataset.version,
                        "tasks": len(dataset.tasks),
                        "sha256": dataset.sha256,
                    }
                )
            )
            return 0
        if args.action == "verify":
            from forge.benchmark.verify import verify_run

            reference = load_dataset(args.dataset) if args.dataset else None
            database = _database() if args.database else None
            try:
                report = verify_run(args.run_dir, reference, database)
            finally:
                if database is not None:
                    database.dispose()
            print(json.dumps(report.to_json(), indent=2))
            return 0 if report.valid else 1
        return _run(args)
    except ForgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted: the run was finalized as cancelled", file=sys.stderr)
        return 130


def _database():  # type: ignore[no-untyped-def]
    from forge.db.session import Database
    from forge.errors import ConfigurationError
    from forge.settings import Settings

    settings = Settings.from_env()
    if settings.database is None:
        raise ConfigurationError("--database needs DATABASE_URL.")
    return Database(settings.database)


def _run(args: argparse.Namespace) -> int:
    from forge.benchmark.runner import BenchmarkRunner, RunOptions
    from forge.db.session import Database
    from forge.errors import ConfigurationError
    from forge.providers.config import load_providers_config
    from forge.providers.router import ProviderRouter
    from forge.settings import Settings

    settings = Settings.from_env()
    router = ProviderRouter(load_providers_config(args.providers), get_secret=settings.get_secret)
    database = None
    if args.database:
        if settings.database is None:
            raise ConfigurationError("--database needs DATABASE_URL.")
        database = Database(settings.database)
    limits = {"max_model_calls": args.max_model_calls}
    if args.max_estimated_tokens is not None:
        limits["max_estimated_tokens"] = args.max_estimated_tokens
    if args.confirm_above_model_calls is not None:
        limits["confirm_above_model_calls"] = args.confirm_above_model_calls
    options = RunOptions(
        dataset=load_dataset(args.dataset),
        target_profile=args.target_model,
        rewriter_profile=args.rewriter_model,
        conditions=tuple(c.strip() for c in args.conditions.split(",") if c.strip()),
        splits=SPLITS if args.split == "all" else (args.split,),
        task_ids=tuple(args.tasks) if args.tasks else None,
        budget_limits=limits,
        output_dir=args.output_dir,
        confirmed=args.confirm,
        allow_real_providers=args.allow_real_providers,
        cache=args.cache,
        cache_scope=args.cache_scope,
        cache_ttl_seconds=settings.cache_ttl_seconds,
        workspace_slug=args.workspace,
    )
    try:
        outcome = BenchmarkRunner(router, database).run(options)
    except ValueError as exc:  # e.g. an unknown condition ID
        raise ConfigurationError(str(exc)) from None
    finally:
        router.close()
        if database is not None:
            database.dispose()
    print(
        json.dumps(
            {
                "run_id": outcome.run_id,
                "status": outcome.status,
                "directory": str(outcome.directory),
                "manifest_sha256": outcome.manifest_sha256,
                "stop_reason": outcome.stop_reason,
                "persistence": outcome.persistence,
                "consistent": outcome.consistent,
                "interpretation": outcome.summary["interpretation"],
            },
            indent=2,
        )
    )
    return 0 if outcome.status == "completed" and outcome.consistent else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
