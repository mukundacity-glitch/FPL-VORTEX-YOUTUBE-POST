"""Supply one official FPL dataset to all Day 3 notebook clients."""
from __future__ import annotations

import io
import hashlib
import json
from concurrent.futures import Future
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlsplit
import urllib.request

from day3.live_evidence import digest


def _endpoint(url):
    parts = urlsplit(url)
    if parts.hostname != "fantasy.premierleague.com" or not parts.path.startswith("/api/"):
        return None
    query = urlencode(sorted((key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                             if key not in {"_", "_vx", "_vortex"}))
    return parts.path.removesuffix("/") + "/" + (f"?{query}" if query else "")


class FrozenFPL:
    def __init__(self, snapshot):
        self._lock = Lock()
        self._sealed = False
        self._missing = set()
        self._responses = {}
        for path, payload in {
            "/bootstrap-static/": snapshot["_bootstrap"],
            "/fixtures/": snapshot["fixtures"],
            **{f"/event/{gw}/live/": rows for gw, rows in snapshot["_event_payloads"].items()},
        }.items():
            future = Future()
            future.set_result((200, json.dumps(payload, allow_nan=False).encode()))
            self._responses[f"/api{path}"] = future

    def _read(self, endpoint, fetch):
        with self._lock:
            future = self._responses.get(endpoint)
            owner = future is None
            if owner:
                if self._sealed:
                    self._missing.add(endpoint)
                    raise RuntimeError(f"Day 3 render requested uncaptured official FPL endpoint: {endpoint}")
                future = self._responses[endpoint] = Future()
        if owner:
            try:
                status, body = fetch()
                # Let the existing collection retries handle transient source errors.
                if status == 429 or status >= 500:
                    with self._lock:
                        del self._responses[endpoint]
                future.set_result((status, body))
            except Exception as error:
                with self._lock:
                    del self._responses[endpoint]
                future.set_exception(error)
        return future.result()

    def seal(self):
        with self._lock:
            self._sealed = True
            responses = list(self._responses.items())
        return digest({key: [status, hashlib.sha256(body).hexdigest()]
                       for key, future in responses
                       for status, body in [future.result()]})

    def verify(self):
        if self._missing:
            raise RuntimeError(f"Day 3 render attempted uncaptured FPL endpoints: {sorted(self._missing)}")

    @contextmanager
    def installed(self):
        import requests

        send = requests.Session.send
        urlopen = urllib.request.urlopen
        following_redirect = ContextVar("day3_following_fpl_redirect", default=False)

        def frozen_send(session, request, **kwargs):
            endpoint = _endpoint(request.url)
            if endpoint is None:
                return send(session, request, **kwargs)
            if request.method != "GET":
                raise RuntimeError("Day 3 only captures public FPL GET requests")
            if following_redirect.get():
                # Requests re-enters Session.send while following a redirect.
                return send(session, request, **kwargs)

            def fetch():
                token = following_redirect.set(True)
                try:
                    with send(session, request, **kwargs) as result:
                        return result.status_code, result.content
                finally:
                    following_redirect.reset(token)

            status, body = self._read(endpoint, fetch)
            response = requests.Response()
            response.status_code = status
            response.url = request.url
            response.request = request
            response.encoding = "utf-8"
            response._content = body
            response._content_consumed = True
            return response

        def frozen_urlopen(request, *args, **kwargs):
            url = request.full_url if isinstance(request, urllib.request.Request) else request
            endpoint = _endpoint(url)
            if endpoint is None:
                return urlopen(request, *args, **kwargs)
            data = args[0] if args else kwargs.get("data")
            method = getattr(request, "method", None)
            if method is None:
                method = "POST" if data is not None or getattr(request, "data", None) is not None else "GET"
            if method != "GET":
                raise RuntimeError("Day 3 only captures public FPL GET requests")

            def fetch():
                try:
                    with urlopen(request, *args, **kwargs) as result:
                        return result.status, result.read()
                except HTTPError as error:
                    with error:
                        return error.code, error.read()

            status, body = self._read(endpoint, fetch)
            response = io.BytesIO(body)
            if status >= 400:
                raise HTTPError(url, status, "Captured FPL response", {}, response)
            response.status = status
            return response

        requests.Session.send = frozen_send
        urllib.request.urlopen = frozen_urlopen
        try:
            yield
        finally:
            requests.Session.send = send
            urllib.request.urlopen = urlopen
