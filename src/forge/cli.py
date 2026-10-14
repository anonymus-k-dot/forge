"""``forge`` command line (also ``python -m forge``).

    forge benchmark validate-dataset DIR
    forge benchmark run --dataset DIR --providers FILE --target-model P [--rewriter-model P]
                        --max-model-calls N [options]          (fake providers only)
    forge benchmark run --experiment FILE [--confirm] [--allow-real-providers]
                        [--output-dir DIR] [--database] [--workspace W]
    forge benchmark verify RUN_DIR [--dataset DIR] [--database]
    forge benchmark plan --experiment FILE [--json]          (offline; never calls a provider)
    forge benchmark export-blind RUN_DIR --experiment FILE --out DIR --key FILE
    forge benchmark analyze RUN_DIR --experiment FILE --key FILE --ratings FILE
                            [--allow-synthetic] [--out DIR]

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
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from forge.benchmark.conditions import CONDITION_IDS
from forge.benchmark.dataset import SPLITS, load_dataset
from forge.errors import ForgeError
from forge.logging import configure_logging

if TYPE_CHECKING:
    from forge.providers.config import ProvidersConfig


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge")
    commands = parser.add_subparsers(dest="command", required=True)
    benchmark = commands.add_parser("benchmark", help="pilot benchmark")
    actions = benchmark.add_subparsers(dest="action", required=True)

    validate = actions.add_parser("validate-dataset", help="validate a task dataset")
    validate.add_argument("dataset", type=Path)

    run = actions.add_parser("run", help="execute a pilot run")
    run.add_argument(
        "--experiment",
        type=Path,
        help="run exactly this experiment config (required for real providers); its "
        "preflight must pass and it defines every option marked (*)",
    )
    run.add_argument("--dataset", type=Path, help="(*)")
    run.add_argument("--providers", type=Path, help="(*) provider config JSON")
    run.add_argument("--target-model", help="(*) model profile for the target")
    run.add_argument("--rewriter-model", help="(*) model profile for B1 and F-legacy rewrites")
    run.add_argument("--conditions", help=f"(*) default {','.join(CONDITION_IDS)}")
    run.add_argument("--split", choices=(*SPLITS, "all"), help="(*) default all")
    run.add_argument("--task", action="append", dest="tasks", help="(*) limit to task ID(s)")
    run.add_argument("--max-model-calls", type=int, help="(*)")
    run.add_argument("--max-estimated-tokens", type=int, help="(*)")
    run.add_argument("--confirm-above-model-calls", type=int, help="(*)")
    run.add_argument("--confirm", action="store_true", help="confirm a run above the threshold")
    run.add_argument("--output-dir", type=Path, default=Path("benchmark-runs"))
    run.add_argument("--database", action="store_true", help="persist to DATABASE_URL")
    run.add_argument("--workspace", default="benchmarks")
    run.add_argument("--cache", action="store_true", help="(*) use the response cache (needs DB)")
    run.add_argument("--cache-scope", help="(*) reuse cached outputs across runs with this scope")
    run.add_argument(
        "--pace-seconds", type=float, help="(*) minimum seconds between model calls (default 0)"
    )
    run.add_argument(
        "--allow-real-providers",
        action="store_true",
        help="permit non-fake providers (real model calls; requires explicit approval and "
        "--experiment)",
    )

    plan = actions.add_parser("plan", help="offline plan and preflight for an experiment")
    plan.add_argument("--experiment", type=Path, required=True)
    plan.add_argument("--json", action="store_true", help="print the plan as JSON")

    export = actions.add_parser("export-blind", help="blinded items for human rating")
    export.add_argument("run_dir", type=Path)
    export.add_argument("--experiment", type=Path, required=True)
    export.add_argument("--out", type=Path, required=True, help="rater folder (items, template)")
    export.add_argument(
        "--key", type=Path, required=True, help="key file, outside --out; never give it to raters"
    )

    analyze = actions.add_parser("analyze", help="paired analysis of a rated run")
    analyze.add_argument("run_dir", type=Path)
    analyze.add_argument("--experiment", type=Path, required=True)
    analyze.add_argument("--key", type=Path, required=True)
    analyze.add_argument("--ratings", type=Path, required=True)
    analyze.add_argument("--allow-synthetic", action="store_true")
    analyze.add_argument("--out", type=Path, help="write analysis.json and analysis.md here")

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
    # Consoles with a legacy code page (e.g. cp1252) must not crash on report text.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="replace")
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
        if args.action == "plan":
            from forge.benchmark.experiment import build_plan, load_experiment, render_plan

            plan_doc = build_plan(
                load_experiment(args.experiment), config_path=args.experiment.as_posix()
            )
            print(json.dumps(plan_doc, indent=2) if args.json else render_plan(plan_doc))
            return 0 if plan_doc["ok"] else 1
        if args.action == "export-blind":
            from forge.benchmark.blinding import export_blind
            from forge.benchmark.experiment import load_experiment

            experiment = load_experiment(args.experiment)
            result = export_blind(
                args.run_dir,
                load_dataset(experiment.dataset.path),
                args.out,
                key_path=args.key,
                seed=experiment.evaluation.blinding_seed,
            )
            print(json.dumps(result, indent=2))
            return 0
        if args.action == "analyze":
            return _analyze(args)
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
    except OSError as exc:  # unreadable input or unwritable output path
        print(f"error: {exc.strerror or type(exc).__name__}: {exc.filename}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted: the run was finalized as cancelled", file=sys.stderr)
        return 130


def _analyze(args: argparse.Namespace) -> int:
    from forge.benchmark.analysis import analyze, render_report
    from forge.benchmark.blinding import load_ratings
    from forge.benchmark.experiment import load_experiment

    experiment = load_experiment(args.experiment)
    report = analyze(
        args.run_dir,
        load_dataset(experiment.dataset.path),
        json.loads(args.key.read_bytes()),
        load_ratings(args.ratings),
        experiment,
        allow_synthetic=args.allow_synthetic,
    )
    if args.out:
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out / "analysis.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (args.out / "analysis.md").write_text(render_report(report), encoding="utf-8")
    print(render_report(report))
    return 0 if report["status"] == "complete" else 1


def _database():  # type: ignore[no-untyped-def]
    from forge.db.session import Database
    from forge.errors import ConfigurationError
    from forge.settings import Settings

    settings = Settings.from_env()
    if settings.database is None:
        raise ConfigurationError("--database needs DATABASE_URL.")
    return Database(settings.database)


# Options an experiment config defines; they cannot also be given on the command line.
_EXPERIMENT_DEFINED = (
    "dataset",
    "providers",
    "target_model",
    "rewriter_model",
    "conditions",
    "split",
    "tasks",
    "max_model_calls",
    "max_estimated_tokens",
    "confirm_above_model_calls",
    "cache_scope",
    "pace_seconds",
)


def _real_providers(providers: ProvidersConfig, profiles: Sequence[str | None]) -> list[str]:
    found = set()
    for name in profiles:
        profile = providers.models.get(name) if name else None
        if profile is not None and providers.providers[profile.provider].type != "fake":
            found.add(profile.provider)
    return sorted(found)


def _run(args: argparse.Namespace) -> int:
    from forge.benchmark.experiment import build_plan, failed_checks, load_experiment
    from forge.benchmark.runner import BenchmarkRunner, RunOptions
    from forge.db.session import Database
    from forge.errors import ConfigurationError
    from forge.providers.config import load_providers_config
    from forge.providers.router import ProviderRouter
    from forge.settings import Settings

    experiment = None
    if args.experiment is not None:
        given = [
            f"--{n.replace('_', '-')}" for n in _EXPERIMENT_DEFINED if getattr(args, n) is not None
        ]
        given += ["--cache"] if args.cache else []
        if given:
            raise ConfigurationError(
                f"{', '.join(given)} cannot be combined with --experiment: the experiment "
                "config defines them."
            )
        experiment = load_experiment(args.experiment)
        # Offline preflight, before any credential is read or adapter built.
        plan = build_plan(experiment, config_path=args.experiment.as_posix())
        if not plan["ok"]:
            raise ConfigurationError(
                f"Experiment {experiment.experiment_id} is not cleared for execution; failed "
                f"checks: {', '.join(failed_checks(plan))}. Nothing was sent. Run "
                "`forge benchmark plan --experiment ...` for details."
            )
        providers = load_providers_config(experiment.providers_file)
        dataset = load_dataset(experiment.dataset.path)
        target_model: str = experiment.target_profile
        rewriter_model: str | None = experiment.rewriter_profile
        conditions: tuple[str, ...] = tuple(experiment.conditions)
        splits: tuple[str, ...] = tuple(experiment.dataset.splits)
        tasks = experiment.dataset.task_ids
        limits: dict[str, int] = experiment.budget.model_dump(exclude_none=True)
        pace, cache, cache_scope = experiment.pace_seconds, False, None
    else:
        missing = [
            f"--{n.replace('_', '-')}"
            for n in ("dataset", "providers", "target_model", "max_model_calls")
            if getattr(args, n) is None
        ]
        if missing:
            raise ConfigurationError(f"run needs {', '.join(missing)} (or --experiment).")
        providers = load_providers_config(args.providers)
        real = _real_providers(providers, (args.target_model, args.rewriter_model))
        if real:
            raise ConfigurationError(
                f"Provider(s) {real} would make real model calls. Real-provider runs are not "
                "authorized without an approved experiment config: use --experiment FILE "
                "(its preflight must pass) with --allow-real-providers, only with explicit "
                "approval."
            )
        dataset = load_dataset(args.dataset)
        target_model, rewriter_model = args.target_model, args.rewriter_model
        conditions = tuple(
            c.strip() for c in (args.conditions or ",".join(CONDITION_IDS)).split(",") if c.strip()
        )
        splits = SPLITS if args.split in (None, "all") else (args.split,)
        tasks = tuple(args.tasks) if args.tasks else None
        limits = {"max_model_calls": args.max_model_calls}
        if args.max_estimated_tokens is not None:
            limits["max_estimated_tokens"] = args.max_estimated_tokens
        if args.confirm_above_model_calls is not None:
            limits["confirm_above_model_calls"] = args.confirm_above_model_calls
        pace, cache, cache_scope = args.pace_seconds or 0.0, args.cache, args.cache_scope

    # Credentials (and DATABASE_URL) may come from a .env file, which is read only when a
    # real provider or the database is used - never for an offline fake-provider run.
    needs_env = args.database or bool(_real_providers(providers, (target_model, rewriter_model)))
    settings = Settings.from_env() if needs_env else Settings.from_env(os.environ)
    router = ProviderRouter(providers, get_secret=settings.get_secret)
    database = None
    if args.database:
        if settings.database is None:
            router.close()
            raise ConfigurationError("--database needs DATABASE_URL.")
        database = Database(settings.database)
    options = RunOptions(
        dataset=dataset,
        target_profile=target_model,
        rewriter_profile=rewriter_model,
        conditions=conditions,
        splits=splits,
        task_ids=tuple(tasks) if tasks else None,
        budget_limits=limits,
        output_dir=args.output_dir,
        confirmed=args.confirm,
        allow_real_providers=args.allow_real_providers,
        cache=cache,
        cache_scope=cache_scope,
        cache_ttl_seconds=settings.cache_ttl_seconds,
        workspace_slug=args.workspace,
        pace_seconds=pace,
        experiment=experiment,
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
