"""Tests for the Autoscaler with mocked Docker, Redis, and Prometheus.

Covers both scaling dimensions:
  * workers  — driven by Redis queue depth (LLEN job_queue)
  * API replicas — driven by each replica's /metrics active_requests
"""

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from autoscaler.autoscaler import Autoscaler


@pytest.fixture(autouse=True)
def mock_prometheus():
    with patch("autoscaler.autoscaler.start_http_server") as m:
        with patch("autoscaler.autoscaler.Counter") as c:
            with patch("autoscaler.autoscaler.Gauge") as g:
                c.return_value = MagicMock()
                g.return_value = MagicMock()
                yield m


@pytest.fixture
def mock_redis():
    with patch("autoscaler.autoscaler.redis.Redis") as m:
        instance = MagicMock()
        instance.ping.return_value = True
        instance.llen.return_value = 0
        m.return_value = instance
        yield instance


@pytest.fixture
def mock_docker():
    with patch("autoscaler.autoscaler.docker.from_env") as m:
        instance = MagicMock()
        instance.ping.return_value = True
        instance.containers.list.return_value = []
        m.return_value = instance
        yield instance


@pytest.fixture
def autoscaler(mock_redis, mock_docker, mock_prometheus):
    with patch.dict("os.environ", {
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
        "REDIS_PASSWORD": "secret",
        "SCALE_UP_THRESHOLD": "10",
        "SCALE_DOWN_THRESHOLD": "3",
        "MIN_WORKERS": "1",
        "MAX_WORKERS": "5",
        "COOLDOWN_SECONDS": "20",
        "API_SCALE_UP_THRESHOLD": "20",
        "API_SCALE_DOWN_THRESHOLD": "5",
        "MIN_API": "1",
        "MAX_API": "5",
        "API_COOLDOWN_SECONDS": "30",
    }):
        a = Autoscaler()
        a.last_worker_scale = 0
        a.last_api_scale = 0
        yield a


class TestAutoscalerInit:
    def test_creds_from_env(self, mock_redis, mock_docker, mock_prometheus):
        with patch.dict("os.environ", {
            "REDIS_HOST": "myredis", "REDIS_PORT": "9999",
            "SCALE_UP_THRESHOLD": "15", "MAX_WORKERS": "7",
            "API_SCALE_UP_THRESHOLD": "42",
        }):
            a = Autoscaler()
            assert a.scale_up_threshold == 15
            assert a.max_workers == 7
            assert a.api_scale_up_threshold == 42

    def test_password_passed_to_redis(self, mock_prometheus, mock_docker):
        with patch.dict(os.environ, {"REDIS_PASSWORD": "secret", "REDIS_HOST": "r1"}):
            with patch("autoscaler.autoscaler.redis.Redis") as cls:
                cls.return_value = MagicMock()
                Autoscaler()
                kwargs = cls.call_args.kwargs
                assert kwargs.get("password") == "secret"
                assert kwargs.get("host") == "r1"

    def test_defaults(self, autoscaler):
        assert autoscaler.min_workers == 1
        assert autoscaler.max_workers == 5
        assert autoscaler.cooldown_seconds == 20
        assert autoscaler.poll_interval == 5


class TestQueueDepth:
    def test_returns_llen(self, autoscaler):
        autoscaler.redis_client.llen.return_value = 42
        assert autoscaler.get_queue_length() == 42

    def test_returns_zero_on_error(self, autoscaler):
        autoscaler.redis_client.llen.side_effect = Exception("boom")
        assert autoscaler.get_queue_length() == 0

    def test_returns_zero_no_redis(self, autoscaler):
        autoscaler.redis_client = None
        assert autoscaler.get_queue_length() == 0


class TestWorkerCount:
    @staticmethod
    def _container(status="running"):
        c = MagicMock()
        c.status = status
        return c

    def test_counts_running_only(self, autoscaler):
        autoscaler.docker_client.containers.list.return_value = [
            self._container("running"), self._container("exited")]
        assert autoscaler.get_current_workers() == 1

    def test_fallback_when_no_docker(self, autoscaler):
        autoscaler.docker_client = None
        autoscaler.current_worker_count = 3
        assert autoscaler.get_current_workers() == 3

    def test_api_count_floor_at_min(self, autoscaler):
        autoscaler.docker_client.containers.list.return_value = []
        assert autoscaler.get_current_api_count() == autoscaler.min_api


class TestApiActiveRequests:
    def test_parses_json_metrics(self, autoscaler):
        container = MagicMock()
        container.status = "running"
        container.attrs = {"NetworkSettings": {"Networks": {
            "net": {"IPAddress": "172.18.0.9"}}}}
        autoscaler.docker_client.containers.list.return_value = [container]
        payload = MagicMock()
        payload.read.return_value = b'{"active_requests": 37, "request_count": 100}'
        with patch("autoscaler.autoscaler.urllib.request.urlopen",
                   return_value=payload):
            assert autoscaler.get_api_active_requests() == 37

    def test_zero_when_unreachable(self, autoscaler):
        container = MagicMock()
        container.status = "running"
        container.attrs = {"NetworkSettings": {"Networks": {
            "net": {"IPAddress": "172.18.0.9"}}}}
        autoscaler.docker_client.containers.list.return_value = [container]
        with patch("autoscaler.autoscaler.urllib.request.urlopen",
                   side_effect=Exception("no route")):
            assert autoscaler.get_api_active_requests() == 0


class TestScaleWorkers:
    def test_skips_if_already_at_target(self, autoscaler):
        autoscaler.current_worker_count = 3
        assert autoscaler.scale_workers(3) is True

    def test_fails_gracefully_no_docker(self, autoscaler):
        autoscaler.current_worker_count = 1
        autoscaler.docker_client = None
        assert autoscaler.scale_workers(5) is False

    def test_scale_up_creates_containers(self, autoscaler):
        template = MagicMock()
        template.status = "running"
        template.attrs = {
            "Config": {"Env": ["FOO=bar"], "Image": "plagioscale-worker:latest"},
            "NetworkSettings": {"Networks": {"plagioscale-network": {}}},
            "Mounts": [],
        }
        autoscaler.docker_client.containers.list.return_value = [template]

        assert autoscaler.scale_workers(2) is True
        assert autoscaler.docker_client.containers.run.call_count == 1
        kwargs = autoscaler.docker_client.containers.run.call_args.kwargs
        assert kwargs["mem_limit"] == "512m"

    def test_scale_down_stops_newest_first(self, autoscaler):
        old = MagicMock()
        old.status = "running"
        old.attrs = {"State": {"StartedAt": "2024-01-01T00:00:01Z"}}
        new = MagicMock()
        new.status = "running"
        new.attrs = {"State": {"StartedAt": "2024-01-01T00:00:02Z"}}
        autoscaler.docker_client.containers.list.return_value = [old, new]
        autoscaler.current_worker_count = 2

        assert autoscaler.scale_workers(1) is True
        new.stop.assert_called_once()
        new.remove.assert_called_once()
        old.stop.assert_not_called()


class TestTickWorkerScaling:
    @staticmethod
    def _running(n=1):
        out = []
        for _ in range(n):
            c = MagicMock()
            c.status = "running"
            out.append(c)
        return out

    def _tick_env(self, a, queue_len, workers=1):
        a.redis_client.llen.return_value = queue_len
        a.docker_client.containers.list.return_value = self._running(workers)

    def test_scales_up_over_threshold(self, autoscaler):
        self._tick_env(autoscaler, queue_len=15, workers=1)
        with patch.object(autoscaler, "scale_workers") as m:
            autoscaler.tick()
            m.assert_called_once_with(2)

    def test_no_scale_up_at_threshold(self, autoscaler):
        self._tick_env(autoscaler, queue_len=10, workers=1)
        with patch.object(autoscaler, "scale_workers") as m:
            autoscaler.tick()
            m.assert_not_called()

    def test_scales_down_under_threshold(self, autoscaler):
        self._tick_env(autoscaler, queue_len=1, workers=3)
        with patch.object(autoscaler, "scale_workers") as m:
            autoscaler.tick()
            m.assert_called_once_with(2)

    def test_no_scale_down_at_min(self, autoscaler):
        self._tick_env(autoscaler, queue_len=0, workers=1)
        with patch.object(autoscaler, "scale_workers") as m:
            autoscaler.tick()
            m.assert_not_called()

    def test_respects_cooldown(self, autoscaler):
        autoscaler.last_worker_scale = time.time() - 5  # cooldown=20
        self._tick_env(autoscaler, queue_len=50, workers=2)
        with patch.object(autoscaler, "scale_workers") as m:
            autoscaler.tick()
            m.assert_not_called()


class TestTickApiScaling:
    def _api_env(self, a, active, count=1):
        container = MagicMock()
        container.status = "running"
        container.attrs = {"Config": {"Image": "img"}, "Mounts": [],
                           "NetworkSettings": {"Networks": {"n": {"IPAddress": "10.0.0.1"}}}}
        a.docker_client.containers.list.return_value = [container] * count
        with patch.object(a, "get_api_active_requests", return_value=active):
            yield a

    def test_scales_up_on_high_active(self, autoscaler):
        for a in self._api_env(autoscaler, active=50):
            with patch.object(a, "scale_api") as m:
                a.tick()
                m.assert_called_once_with(2)

    def test_no_action_below_threshold(self, autoscaler):
        for a in self._api_env(autoscaler, active=5):
            with patch.object(a, "scale_api") as m:
                a.tick()
                m.assert_not_called()

    def test_respects_api_cooldown(self, autoscaler):
        autoscaler.last_api_scale = time.time() - 10  # cooldown=30
        for a in self._api_env(autoscaler, active=50):
            with patch.object(a, "scale_api") as m:
                a.tick()
                m.assert_not_called()


class TestEvents:
    def test_publish_event_pushes_and_trims(self, autoscaler):
        rc = MagicMock()
        autoscaler.redis_client = rc
        autoscaler.publish_event("info", "Scaled workers to 3", workers=3)
        rc.lpush.assert_called_once()
        rc.ltrim.assert_called_once_with("autoscaler_events", 0, 99)
        key, payload = rc.lpush.call_args.args
        assert key == "autoscaler_events"
        assert "Scaled workers to 3" in payload

    def test_publish_event_never_raises(self, autoscaler):
        autoscaler.redis_client = None  # must not raise
        autoscaler.publish_event("info", "noop")
