import json
import logging
from pathlib import Path

import yaml

from jarvis.agents import AgentDefinition

logger = logging.getLogger(__name__)


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
    except Exception as e:
        logger.warning("Failed to parse %s: %s", f, e)
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
    except Exception as e:
        logger.warning("Failed to parse %s: %s", f, e)
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
        front = yaml.safe_load(parts[1])
        instructions = "---".join(parts[2:]).strip()
        return AgentDefinition(
            name=front.get("name", agent_dir.name),
            description=front.get("description", ""),
            instructions=instructions,
            source_file=str(skill_md),
        )
    except Exception as e:
        logger.warning("Failed to parse %s: %s", skill_md, e)
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
