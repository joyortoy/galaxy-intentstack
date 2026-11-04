import pytest

from galaxy_intentstack import Action, Engine, Message

TOKEN = "operator-token-00000000000000000000000000"
REVIEWER = "reviewer-token-0000000000000000000000000"


@pytest.fixture
def engine(tmp_path):
    e = Engine(tmp_path / "integrity.db", clock=lambda: 1000.0)
    e.authority.enroll("user", TOKEN)
    e.authority.enroll("reviewer", REVIEWER, ["approve", "verify"])
    return e


@pytest.fixture
def action():
    return Action(kind="schedule", resource="meeting:1", scope="write")


def send(e, text, event="one", **kwargs):
    source = kwargs.pop("source", "sender")
    token = kwargs.pop("token", None)
    return e.process(
        Message(event_id=event, session="s", text=text, **kwargs), source=source, token=token
    )
