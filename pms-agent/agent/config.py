import os
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict


CONFIG_PATH = Path(os.environ.get("PMS_CONFIG_PATH", "/etc/pms-agent/config.json"))


@dataclass
class AgentConfig:
    server_url: str = "http://localhost:8000"
    enrollment_token: str = ""
    agent_token: str = ""
    endpoint_id: str = ""
    agent_version: str = "0.1.0"
    heartbeat_interval: int = 300       # seconds
    inventory_interval: int = 1800      # seconds
    log_path: str = "/var/log/pms-agent.log"
    ca_cert_path: str = ""              # path to server CA cert for pinning

    def save(self, path: Path = CONFIG_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "AgentConfig":
        if path.exists():
            data = json.loads(path.read_text())
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        return cls()
