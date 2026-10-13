"""``forge benchmark`` command line (offline only)."""

import json
from pathlib import Path

from forge.cli import main
from tests.benchmark.helpers import OFFLINE_PROVIDERS, PILOT_DIR


def offline_args(tmp_path, *extra):
    return [
        "benchmark",
        "run",
        "--dataset",
        str(PILOT_DIR),
        "--providers",
        str(OFFLINE_PROVIDERS),
        "--target-model",
        "offline-target",
        "--rewriter-model",
        "offline-rewriter",
        "--output-dir",
        str(tmp_path),
        *extra,
    ]


def test_validate_dataset(capsys, tmp_path):
    assert main(["benchmark", "validate-dataset", str(PILOT_DIR)]) == 0
    assert json.loads(capsys.readouterr().out)["tasks"] == 30
    assert main(["benchmark", "validate-dataset", str(tmp_path)]) == 2
    assert "metadata not found" in capsys.readouterr().err


def test_offline_run_then_verify(capsys, tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert main(offline_args(tmp_path, "--max-model-calls", "150")) == 0
    result = json.loads(capsys.readouterr().out)
    assert (result["status"], result["interpretation"]) == ("completed", "INCONCLUSIVE")
    assert main(["benchmark", "verify", result["directory"], "--dataset", str(PILOT_DIR)]) == 0
    assert json.loads(capsys.readouterr().out)["complete"] is True


def test_subset_run_with_split_and_conditions(capsys, tmp_path):
    args = offline_args(tmp_path, "--max-model-calls", "10", "--split", "heldout")
    args += ["--conditions", "B0"]
    assert main(args) == 0
    directory = Path(json.loads(capsys.readouterr().out)["directory"])
    assert directory.parent == tmp_path
    assert len((directory / "results.jsonl").read_text().splitlines()) == 10  # 10 held-out


def test_insufficient_budget_and_unknown_condition_are_usage_errors(capsys, tmp_path):
    assert main(offline_args(tmp_path, "--max-model-calls", "10")) == 2
    assert "budget" in capsys.readouterr().err
    assert main(offline_args(tmp_path, "--max-model-calls", "150", "--conditions", "B9")) == 2
    assert "unknown condition" in capsys.readouterr().err
    assert not any(tmp_path.iterdir())


def test_real_provider_configuration_is_refused(capsys, tmp_path):
    # The packaged default config targets the Gemini API: refused without the explicit flag.
    args = [
        "benchmark",
        "run",
        "--dataset",
        str(PILOT_DIR),
        "--providers",
        "src/forge/providers/default_providers.json",
        "--target-model",
        "legacy-enhancer",
        "--max-model-calls",
        "150",
        "--conditions",
        "B0",
        "--output-dir",
        str(tmp_path),
    ]
    assert main(args) == 2
    assert "not authorized" in capsys.readouterr().err
    assert not any(tmp_path.iterdir())


def test_cache_requires_database(capsys, tmp_path):
    assert main(offline_args(tmp_path, "--max-model-calls", "150", "--cache")) == 2
    assert "requires --database" in capsys.readouterr().err
