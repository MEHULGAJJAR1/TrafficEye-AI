import time

import pytest
from fastapi.testclient import TestClient

from backend.app.config import ROOT, Settings
from backend.app.main import create_app

TEST_KEY = "integration-test-key-not-a-real-credential-1234"


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data", model_dir=tmp_path / "models", sample_dir=ROOT / "samples", api_key=TEST_KEY, max_upload_mb=1, max_queued_jobs=1, demo_delay=.006)


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as connection:
        assert connection.post("/api/auth/login", json={"key": TEST_KEY}).status_code == 200
        yield connection


def wait_job(client, job_id, states=("completed", "failed", "cancelled"), timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200, response.text
        job = response.json()
        if job["status"] in states:
            return job
        time.sleep(.015)
    raise AssertionError(f"Job did not reach {states}: {job}")


def sample(client):
    result = client.post("/api/samples/demo")
    assert result.status_code == 201, result.text
    return result.json()


def complete_demo(client, seconds=6):
    job = sample(client)
    response = client.post(f"/api/jobs/{job['id']}/start", json={"mode": "demo", "max_seconds": seconds})
    assert response.status_code == 200, response.text
    result = wait_job(client, job["id"])
    assert result["status"] == "completed", result
    return result
