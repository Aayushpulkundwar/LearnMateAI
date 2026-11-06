"""Exercise the Windows runner with a process double; never invoke Docker."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")
pytestmark = pytest.mark.skipif(not POWERSHELL, reason="PowerShell required")
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def runner(tmp_path):
    scripts = tmp_path / "research/scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(ROOT / "research/scripts/RUN_RAG_COMPARISON.ps1", scripts / "RUN_RAG_COMPARISON.ps1")
    # Only this test double is sourced by the copied runner. All external calls
    # are recorded; output transfer creates explicitly synthetic fixture files.
    (scripts / "Invoke-ResearchDocker.ps1").write_text('''
function Invoke-ResearchProcess {
  param([string[]]$DockerArguments, [string]$LogPath, [string]$Executable = 'docker')
  Add-Content -LiteralPath ($LogPath + '.calls') -Value (ConvertTo-Json -Compress -InputObject @{exe=$Executable; args=$DockerArguments})
  if ($DockerArguments[3] -eq 'cp' -and $DockerArguments[4] -like 'api:*/output/runs/*.json') {
    Set-Content -LiteralPath $DockerArguments[5] -Value 'synthetic test fixture'
  }
}
''', encoding="utf-8")
    for relative in (
        "research/results/nine_science_03/corpus.json",
        "research/results/nine_science_03/environment.json",
        "research/results/nine_science_03/ollama_models.json",
        "research/results/nine_science_03/questions.candidates.jsonl",
        "research/experiments/rag_comparison/datasets/questions.jsonl",
        "research/experiments/rag_comparison/datasets/dataset_report.json",
        "research/experiments/rag_comparison/system_configuration.json",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    (tmp_path / "backend").mkdir()
    return tmp_path


def run_runner(root):
    result = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                             str(root / "research/scripts/RUN_RAG_COMPARISON.ps1"),
                             "-RunId", "staging_test"], capture_output=True, text=True)
    calls_path = root / "research/experiments/rag_comparison/execution.log.calls"
    calls = [json.loads(line) for line in calls_path.read_text(encoding="utf-8-sig").splitlines()] if calls_path.exists() else []
    return result, calls


def test_runner_stages_all_inputs_before_retrieval_and_copies_outputs_to_host(runner):
    result, calls = run_runner(runner)
    assert result.returncode == 0, result.stderr
    retrieve_index = next(i for i, c in enumerate(calls) if "retrieve" in c["args"])
    staged = [c["args"] for c in calls[:retrieve_index] if c["args"][3] == "cp"]
    for name in ("corpus.json", "environment.json", "ollama_models.json", "questions.jsonl"):
        assert any(args[5] == f"api:/tmp/learnmate-rag-staging_test/frozen/{name}" and Path(args[4]).name == name for args in staged)
    for mode in ("dense", "fts", "hybrid"):
        target = runner / f"research/experiments/rag_comparison/runs/{mode}.json"
        assert any(c["args"][3:] == ["cp", f"api:/tmp/learnmate-rag-staging_test/output/runs/{mode}.json", str(target)] for c in calls[retrieve_index + 1:])
        assert target.read_text().strip() == "synthetic test fixture"


def test_runner_lists_missing_metadata_without_launching_any_process(runner):
    for name in ("environment.json", "ollama_models.json"):
        (runner / "research/results/nine_science_03" / name).unlink()
    result, calls = run_runner(runner)
    assert result.returncode != 0
    assert "environment.json" in result.stderr
    assert "ollama_models.json" in result.stderr
    assert calls == []


def test_runner_refuses_existing_research_output(runner):
    target = runner / "research/experiments/rag_comparison/runs/dense.json"
    target.parent.mkdir()
    target.write_text("existing evidence", encoding="utf-8")
    result, calls = run_runner(runner)
    assert result.returncode != 0
    assert "Refusing to overwrite" in result.stderr
    assert calls == []
    assert target.read_text() == "existing evidence"
