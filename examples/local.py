"""Run after installing the package: python examples/local.py"""

import tempfile
from pathlib import Path

from galaxy_intentstack import Engine, Message

with tempfile.TemporaryDirectory() as directory:
    engine = Engine(Path(directory) / "example.db")
    print(
        engine.process(
            Message(
                event_id="example-1",
                session="example",
                text="Every galaxy began as something too small to notice.",
            )
        ).model_dump_json(indent=2)
    )
