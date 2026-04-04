from pathlib import Path


def _workflow_text(name: str) -> str:
    return Path(f".github/workflows/{name}.yml").read_text(encoding="utf-8")


def test_verify_workflow_triggers_on_push_pull_request_and_workflow_call():
    workflow = _workflow_text("verify")

    assert "push:" in workflow
    assert "pull_request:" in workflow
    assert "workflow_call:" in workflow


def test_verify_workflow_runs_docker_suite_builds_artifacts_and_uploads_dist():
    workflow = _workflow_text("verify")

    assert "docker compose -f docker/docker-compose.yml build app" in workflow
    assert "docker compose -f docker/docker-compose.yml run --rm app uv run pytest -v" in workflow
    assert "uv build" in workflow
    assert "scripts/release/smoke_test_installed_package.py" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "name: dist-artifacts" in workflow
