from app.event_store import EventStore
from app.queries.identity import get_user_by_email
from app.replay import rebuild_read_models
from tests.conftest import register


def test_studio_tools_called_over_mcp(app, client):
    from agent.mcp_client import call_studio_tool

    profile = call_studio_tool(
        "extract_resume_profile",
        {"cv_text": "Dana\ndana@x.test\nPython Flask 5 years at NovaLabs\n"},
    )
    assert "dana@x.test" in profile.get("emails", [])
    assert "python" in profile.get("skills", [])


def test_replay_rebuilds_users_from_events(app, client):
    register(client, "replay@x.test", "candidate", "Replay User")
    with app.app_context():
        EventStore.append(
            "UserRegistered",
            "User",
            "deadbeef-replay",
            {
                "email": "second@x.test",
                "password_hash": "x",
                "full_name": "Second",
                "role": "hr",
            },
        )
        n = rebuild_read_models()
        assert n >= 2
        assert get_user_by_email("replay@x.test")["full_name"] == "Replay User"
        assert get_user_by_email("second@x.test")["role"] == "hr"
