from dataclasses import dataclass

from .directory import DCFSDirectory


@dataclass
class DCFSMetadata:
    dir: DCFSDirectory

    @staticmethod
    def from_dict(data: dict) -> "DCFSMetadata":
        return DCFSMetadata(
            dir=DCFSDirectory.from_dict(data["dir"]),
        )

    def to_dict(self) -> dict:
        return {
            "type": "DCFSMetadata",
            "dir": self.dir.to_dict(),
        }
