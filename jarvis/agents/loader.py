import json
import logging
from pathlib import Path

import yaml

from jarvis.agents import AgentDefinition
from jarvis.logging_config import format_log_tags

logger = logging.getLogger(__name__)


def _log_parse_failure(path: Path, error: Exception) -> None:
    logger.warning(
        "%s Failed to parse Agent definition file=%s",
        format_log_tags(
            ("组件", "Agent加载器"),
            ("结果", "失败"),
            ("错误", type(error).__name__),
        ),
        path,
    )


def _parse_json(agent_dir: Path) -> AgentDefinition | None:
    f = agent_dir / "agent.json"
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text())
        return AgentDefinition(
            name=data["name"],
            description=data.get("description", ""),
            instructions=data.get("instructions", ""),
            source_file=str(f),
        )
    except Exception as error:
        _log_parse_failure(f, error)
        return None


def _parse_yaml(agent_dir: Path) -> AgentDefinition | None:
    f = agent_dir / "agent.yaml"
    if not f.exists():
        return None
    try:
        data = yaml.safe_load(f.read_text())
        return AgentDefinition(
            name=data["name"],
            description=data.get("description", ""),
            instructions=data.get("instructions", ""),
            source_file=str(f),
        )
    except Exception as error:
        _log_parse_failure(f, error)
        return None


def _parse_claude(agent_dir: Path) -> AgentDefinition | None:
    skill_md = agent_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    try:
        raw = skill_md.read_text()
        # extract frontmatter between --- delimiters
        parts = raw.split("---")
        if len(parts) < 3:
            return None
        front = yaml.safe_load(parts[1]) or {}
        openai_yaml = agent_dir / "agents" / "openai.yaml"
        interface = {}
        if openai_yaml.exists():
            openai_data = yaml.safe_load(openai_yaml.read_text()) or {}
            interface = openai_data.get("interface", {}) or {}
        instructions = "---".join(parts[2:]).strip()
        return AgentDefinition(
            name=front.get("name") or interface.get("display_name") or agent_dir.name,
            description=front.get("description") or interface.get("short_description") or "",
            instructions=instructions,
            source_file=str(skill_md),
        )
    except Exception as error:
        _log_parse_failure(skill_md, error)
        return None


def load_agents(agents_dir: str) -> list[AgentDefinition]:
    root = Path(agents_dir)
    if not root.exists() or not root.is_dir():
        return []

    results: list[AgentDefinition] = []
    for agent_dir in sorted(root.iterdir()):
        if not agent_dir.is_dir():
            continue
        agent = (
            _parse_json(agent_dir)
            or _parse_yaml(agent_dir)
            or _parse_claude(agent_dir)
        )
        if agent is not None:
            results.append(agent)
    return results
