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


def test_external_llm_config_mount_and_generator_agree():
    documents = list(yaml.safe_load_all((ROOT / "jarvis.yaml").read_text()))
    config = next(doc for doc in documents if doc and doc.get("kind") == "ConfigMap")
    deployment = next(doc for doc in documents if doc and doc.get("kind") == "Deployment")
    spec = deployment["spec"]["template"]["spec"]
    container = _jarvis_container()
    mount = next(m for m in container["volumeMounts"] if m["name"] == "llm-config")
    volume = next(v for v in spec["volumes"] if v["name"] == mount["name"])
    generator = yaml.safe_load((ROOT / "kustomization.yaml").read_text())
    generated = next(g for g in generator["configMapGenerator"] if g["name"] == volume["configMap"]["name"])
    assert generated["files"] == ["llm.yaml"]
    assert mount["readOnly"] is True
    assert "subPath" not in mount
    assert config["data"]["LLM_CONFIG_PATH"] == mount["mountPath"] + "/llm.yaml"
    assert volume["configMap"]["items"] == [{"key": "llm.yaml", "path": "llm.yaml"}]
    assert not generator.get("generatorOptions", {}).get("disableNameSuffixHash", False)


def test_model_administration_uses_separate_secret_reference():
    documents = list(yaml.safe_load_all((ROOT / "jarvis.yaml").read_text()))
    config = next(doc for doc in documents if doc and doc.get("kind") == "ConfigMap")
    assert config["data"]["LLM_RUNTIME_CONFIG_ENABLED"] == "true"
    assert "JARVIS_ADMIN_TOKEN" not in config["data"]
    env = next(e for e in _jarvis_container()["env"] if e["name"] == "JARVIS_ADMIN_TOKEN")
    assert "value" not in env
    assert env["valueFrom"]["secretKeyRef"] == {"name": "jarvis-admin", "key": "JARVIS_ADMIN_TOKEN"}
    assert not any(doc and doc.get("kind") == "Secret" for doc in documents)
