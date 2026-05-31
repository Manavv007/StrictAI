from app import interviewer


class _Msg:
    content = "Tell me about a project you're proud of."


class _Choice:
    message = _Msg()


class _Resp:
    choices = [_Choice()]


class _FakeClient:
    class chat:
        class completions:
            @staticmethod
            def create(**kwargs):
                return _Resp()


def test_interviewer_replies(monkeypatch):
    monkeypatch.setattr(interviewer, "_get_client", lambda: _FakeClient)
    out = interviewer.reply([{"role": "user", "content": "Hi"}])
    assert isinstance(out, str) and out
    # never raises on empty history
    assert isinstance(interviewer.reply([]), str)
