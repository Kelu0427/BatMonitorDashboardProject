from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict

from .constants import DEFAULT_GEOMETRY, DEFAULT_LOG_MAX_MB, task_id


@dataclass
class MonitorTask:
    task_id: str
    name: str
    bat_path: str
    workdir: str
    auto_start: bool
    max_lines: int
    log_max_mb: int
    output_encoding: str
    inline_launch: bool
    kill_port_before_start: bool
    kill_port: int
    geometry: Dict[str, int]

    @classmethod
    def from_dict(cls, data: Dict) -> "MonitorTask":
        bat_path = str(data.get("bat_path", "")).strip()
        workdir = str(data.get("workdir", "")).strip()
        if not workdir and bat_path:
            workdir = str(Path(bat_path).expanduser().parent)
        geometry = dict(DEFAULT_GEOMETRY)
        geometry.update(data.get("geometry", {}) if isinstance(data.get("geometry"), dict) else {})
        return cls(
            task_id=str(data.get("task_id", task_id())),
            name=str(data.get("name", "")).strip() or "未命名監控",
            bat_path=bat_path,
            workdir=workdir,
            auto_start=bool(data.get("auto_start", True)),
            max_lines=max(100, int(data.get("max_lines", 3000))),
            log_max_mb=max(1, int(data.get("log_max_mb", DEFAULT_LOG_MAX_MB))),
            output_encoding=str(data.get("output_encoding", "utf-8")).strip() or "utf-8",
            inline_launch=bool(data.get("inline_launch", False)),
            kill_port_before_start=bool(data.get("kill_port_before_start", False)),
            kill_port=max(0, min(65535, int(data.get("kill_port", 0)))),
            geometry={
                "x": int(geometry.get("x", DEFAULT_GEOMETRY["x"])),
                "y": int(geometry.get("y", DEFAULT_GEOMETRY["y"])),
                "w": max(240, int(geometry.get("w", DEFAULT_GEOMETRY["w"]))),
                "h": max(160, int(geometry.get("h", DEFAULT_GEOMETRY["h"]))),
            },
        )

    def to_dict(self) -> Dict:
        return asdict(self)
