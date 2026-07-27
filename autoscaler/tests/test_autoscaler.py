"""Tests for QueueBasedAutoscaler with mocked Docker, Redis, and Prometheus."""

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from autoscaler.autoscaler import QueueBasedAutoscaler


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
        "SCALE_UP_THRESHOLD": "10",
        "SCALE_DOWN_THRESHOLD": "3",
        "MIN_WORKERS": "1",
        "MAX_WORKERS": "5",
        "COOLDOWN_SECONDS": "0",
    }):
        a = QueueBasedAutoscaler()
        a.last_scale_time = 0
        yield a


class TestAutoscalerInit:
    def test_creds_from_env(self, mock_redis, mock_docker, mock_prometheus):
        with patch.dict("os.environ", {
            "REDIS_HOST": "myredis", "REDIS_PORT": "9999",
            "SCALE_UP_THRESHOLD": "20", "SCALE_DOWN_THRESHOLD": "5",
            "MIN_WORKERS": "2", "MAX_WORKERS": "10", "COOLDOWN_SECONDS": "30",
        }):
            a = QueueBasedAutoscaler()
            assert a.redis_host == "myredis"
            assert a.redis_port == 9999
            assert a.scale_up_threshold == 20
            assert a.scale_down_threshold == 5
            assert a.min_workers == 2
            assert a.max_workers == 10
            assert a.cooldown_seconds == 30

    def test_creds_defaults(self, mock_redis, mock_docker, mock_prometheus):
        with patch.dict("os.environ", {"PATH": os.environ.get("PATH", "")}, clear=True):
            a = QueueBasedAutoscaler()
            assert a.redis_host == "redis"
            assert a.redis_port == 6379
            assert a.min_workers == 1
            assert a.max_workers == 5
            assert a.cooldown_seconds == 60


class TestQueueLength:
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
    def test_returns_docker_count(self, autoscaler):
        container = MagicMock()
        container.status = "running"
        container.attrs = {"State": {"StartedAt": "2024-01-01T00:00:00Z"}}
        autoscaler.docker_client.containers.list.return_value = [container, container]
        count = autoscaler.get_current_workers()
        assert count == 2

    def test_filters_running_only(self, autoscaler):
        running = MagicMock()
        running.status = "running"
        stopped = MagicMock()
        stopped.status = "exited"
        autoscaler.docker_client.containers.list.return_value = [running, stopped]
        assert autoscaler.get_current_workers() == 1

    def test_fallback_to_min_on_error(self, autoscaler):
        autoscaler.docker_client = None
        autoscaler.current_worker_count = 3
        assert autoscaler.get_current_workers() == 3


class TestScaleDecisions:
    def test_should_scale_up_when_over_threshold(self, autoscaler):
        autoscaler.current_worker_count = 1
        assert autoscaler.should_scale_up(15) is True

    def test_should_not_scale_up_at_threshold(self, autoscaler):
        autoscaler.current_worker_count = 1
        assert autoscaler.should_scale_up(10) is False

    def test_should_not_scale_up_at_max(self, autoscaler):
        autoscaler.current_worker_count = 5
        assert autoscaler.should_scale_up(20) is False

    def test_should_scale_down_when_below_threshold(self, autoscaler):
        autoscaler.current_worker_count = 3
        assert autoscaler.should_scale_down(2) is True

    def test_should_not_scale_down_at_threshold(self, autoscaler):
        autoscaler.current_worker_count = 3
        assert autoscaler.should_scale_down(3) is False

    def test_should_not_scale_down_at_min(self, autoscaler):
        autoscaler.current_worker_count = 1
        assert autoscaler.should_scale_down(0) is False

    def test_can_scale_now_respects_cooldown(self, autoscaler):
        autoscaler.cooldown_seconds = 60
        autoscaler.last_scale_time = time.time() - 30
        assert autoscaler.can_scale_now() is False

    def test_can_scale_now_after_cooldown(self, autoscaler):
        autoscaler.cooldown_seconds = 60
        autoscaler.last_scale_time = time.time() - 120
        assert autoscaler.can_scale_now() is True


class TestScaleWorkers:
    def test_skips_if_already_at_target(self, autoscaler):
        autoscaler.current_worker_count = 3
        assert autoscaler.scale_workers(3) is True

    def test_fails_gracefully_no_docker(self, autoscaler):
        autoscaler.docker_client = None
        assert autoscaler.scale_workers(5) is False

    def test_scale_up_creates_containers(self, autoscaler):
        template = MagicMock()
        template.image = "plagioscale-worker:latest"
        template.attrs = {
            "Config": {"Env": ["FOO=bar", "WORKER_ID=worker-1"], "Image": "plagioscale-worker:latest"},
            "NetworkSettings": {"Networks": {"plagioscale-network": {}}},
            "Mounts": [],
        }
        autoscaler.docker_client.containers.list.return_value = [template]

        result = autoscaler.scale_workers(3)

        assert result is True
        assert autoscaler.current_worker_count == 3
        assert autoscaler.docker_client.containers.run.call_count >= 1

    def test_scale_down_stops_containers(self, autoscaler):
        c1 = MagicMock()
        c1.status = "running"
        c1.name = "plagioscale-worker-1"
        c1.attrs = {"State": {"StartedAt": "2024-01-01T00:00:01Z"}}
        c2 = MagicMock()
        c2.status = "running"
        c2.name = "plagioscale-worker-2"
        c2.attrs = {"State": {"StartedAt": "2024-01-01T00:00:02Z"}}
        autoscaler.docker_client.containers.list.return_value = [c1, c2]
        autoscaler.current_worker_count = 2

        result = autoscaler.scale_workers(1)

        assert result is True
        c2.stop.assert_called_once()
        c2.remove.assert_called_once()


class TestTick:
    def test_tick_does_not_scale_during_cooldown(self, autoscaler):
        autoscaler.cooldown_seconds = 9999
        autoscaler.last_scale_time = time.time()
        autoscaler.redis_client.llen.return_value = 50
        with patch.object(autoscaler, "scale_workers") as mock_scale:
            autoscaler.tick()
            mock_scale.assert_not_called()

    def test_tick_scales_up_when_needed(self, autoscaler):
        autoscaler.redis_client.llen.return_value = 50
        worker = MagicMock()
        worker.status = "running"
        worker.attrs = {"State": {"StartedAt": "2024-01-01T00:00:01Z"}}
        autoscaler.docker_client.containers.list.return_value = [worker]
        autoscaler.current_worker_count = 1
        with patch.object(autoscaler, "scale_workers") as mock_scale:
            autoscaler.tick()
            mock_scale.assert_called_once_with(2)

    def test_tick_scales_down_when_needed(self, autoscaler):
        autoscaler.redis_client.llen.return_value = 1
        workers = []
        for i in range(3):
            w = MagicMock()
            w.status = "running"
            w.attrs = {"State": {"StartedAt": f"2024-01-01T00:00:0{i+1}Z"}}
            workers.append(w)
        autoscaler.docker_client.containers.list.return_value = workers
        autoscaler.current_worker_count = 3
        with patch.object(autoscaler, "scale_workers") as mock_scale:
            autoscaler.tick()
            mock_scale.assert_called_once_with(2)
