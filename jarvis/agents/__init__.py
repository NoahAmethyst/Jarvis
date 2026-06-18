from dataclasses import dataclass


@dataclass
class AgentDefinition:
    name: str
    description: str
    instructions: str
    source_file: str
