import hashlib
import io
import zipfile
from urllib.error import HTTPError, URLError

import pytest

import install

URL = "https://example.invalid/release.zip"


def zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("MaaFramework.dll", b"fixed")
    return buffer.getvalue()


def http(code: int) -> HTTPError:
    return HTTPError(URL, code, "Gateway Timeout" if code == 504 else "Not Found", {}, None)


def serve(monkeypatch, answers):
    """urlopen gives each call the next answer, raising it when it is an exception; sleep only records the wait."""
    calls, waits, answers = [], [], iter(answers)

    def urlopen(url, timeout=None):
        calls.append(url)
        answer = next(answers)
        if isinstance(answer, BaseException):
            raise answer
        return io.BytesIO(answer)

    monkeypatch.setattr(install, "urlopen", urlopen)
    monkeypatch.setattr(install, "sleep", waits.append, raising=False)
    return calls, waits


@pytest.mark.parametrize("error", [http(500), http(504), URLError(TimeoutError("timed out")), TimeoutError("timed out")],
                         ids=["500", "504", "connect timeout", "read timeout"])
def test_a_5xx_or_a_timeout_is_tried_again_until_the_zip_comes(monkeypatch, capsys, error):
    data = zip_bytes()
    calls, waits = serve(monkeypatch, [error, data])
    assert install.fetch_zip(URL, hashlib.sha256(data).hexdigest()).read("MaaFramework.dll") == b"fixed"
    assert len(calls) == 2 and len(waits) == 1 and waits[0] > 0
    [line] = capsys.readouterr().out.splitlines()
    assert URL in line


def test_the_last_try_fails_after_waits_that_grow(monkeypatch, capsys):
    calls, waits = serve(monkeypatch, (http(503) for _ in range(100)))
    with pytest.raises(HTTPError):
        install.fetch_zip(URL, "0" * 64)
    assert len(waits) >= 2 and waits == sorted(set(waits))
    assert len(calls) == len(waits) + 1
    assert len(capsys.readouterr().out.splitlines()) == len(waits)


def test_a_4xx_is_not_tried_again(monkeypatch):
    """Guards what origin/main already does: one request, no wait."""
    calls, waits = serve(monkeypatch, [http(404), zip_bytes()])
    with pytest.raises(HTTPError):
        install.fetch_zip(URL, "0" * 64)
    assert len(calls) == 1 and waits == []
