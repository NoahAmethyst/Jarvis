from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _jarvis_container() -> dict:
    documents = yaml.safe_load_all((ROOT / "jarvis.yaml").read_text(encoding="utf-8"))
    deployment = next(
        document
        for document in documents
        if document and document.get("kind") == "Deployment"
    )
    return next(
        container
        for container in deployment["spec"]["template"]["spec"]["containers"]
        if container["name"] == "jarvis"
    )


def test_kubernetes_uses_dedicated_health_probe_paths():
    container = _jarvis_container()

    assert container["readinessProbe"]["httpGet"]["path"] == "/health/ready"
    assert container["livenessProbe"]["httpGet"]["path"] == "/health/live"


def test_docker_healthcheck_uses_liveness_endpoint():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    healthcheck = dockerfile.split("HEALTHCHECK", 1)[1].split("CMD [", 1)[0]

    assert "/health/live" in healthcheck
    assert "/docs" not in healthcheck


def test_llm_alert_configuration_is_available_and_opt_in():
    documents = yaml.safe_load_all((ROOT / "jarvis.yaml").read_text(encoding="utf-8"))
    config = next(doc for doc in documents if doc and doc.get("kind") == "ConfigMap")
    assert config["data"]["QQBOT_GRPC_TARGET"] == "qq-bot:9090"
    assert config["data"]["LLM_ERROR_QQ_USER_ID"] == ""
