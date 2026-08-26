from unittest.mock import MagicMock, patch

from shared.models import Job, JobStatus


class TestQueueClient:
    @patch("shared.queue_client.redis.Redis")
    def test_enqueue_job(self, mock_redis):
        from shared.queue_client import QueueClient

        client = QueueClient()
        client.redis_client = MagicMock()
        mock_pipe = MagicMock()
        client.redis_client.pipeline.return_value = mock_pipe

        job = Job(job_id="test-123", text="hello world")
        result = client.enqueue_job(job)

        assert result is True
        client.redis_client.pipeline.assert_called_once()
        mock_pipe.lpush.assert_called_once()
        mock_pipe.hset.assert_called_once()
        mock_pipe.execute.assert_called_once()

    @patch("shared.queue_client.redis.Redis")
    def test_dequeue_job(self, mock_redis):
        from shared.queue_client import QueueClient

        client = QueueClient()
        client.redis_client = MagicMock()

        job = Job(job_id="test-456", text="dequeue me")
        client.redis_client.brpop.return_value = ("job_queue", job.to_json())

        result = client.dequeue_job(timeout=5)
        assert result is not None
        assert result.job_id == "test-456"
        assert result.text == "dequeue me"

    @patch("shared.queue_client.redis.Redis")
    def test_dequeue_job_empty(self, mock_redis):
        from shared.queue_client import QueueClient

        client = QueueClient()
        client.redis_client = MagicMock()
        client.redis_client.brpop.return_value = None

        result = client.dequeue_job(timeout=5)
        assert result is None

    @patch("shared.queue_client.redis.Redis")
    def test_get_queue_length(self, mock_redis):
        from shared.queue_client import QueueClient

        client = QueueClient()
        client.redis_client = MagicMock()
        client.redis_client.llen.return_value = 5

        length = client.get_queue_length()
        assert length == 5

    @patch("shared.queue_client.redis.Redis")
    def test_update_job_status(self, mock_redis):
        from shared.queue_client import QueueClient

        client = QueueClient()
        client.redis_client = MagicMock()

        result = client.update_job_status("test-789", JobStatus.PROCESSING)
        assert result is True
        client.redis_client.hset.assert_called_once()

    @patch("shared.queue_client.redis.Redis")
    def test_store_result(self, mock_redis):
        from shared.queue_client import QueueClient

        client = QueueClient()
        client.redis_client = MagicMock()

        result_data = {"score": 0.85}
        result = client.store_result("test-abc", result_data)
        assert result is True

    @patch("shared.queue_client.redis.Redis")
    def test_get_job_status(self, mock_redis):
        from shared.queue_client import QueueClient

        client = QueueClient()
        client.redis_client = MagicMock()
        client.redis_client.hget.return_value = "COMPLETED"

        status = client.get_job_status("test-xyz")
        assert status == "COMPLETED"

    @patch("shared.queue_client.redis.Redis")
    def test_enqueue_job_failure(self, mock_redis):
        from shared.queue_client import QueueClient

        client = QueueClient()
        client.redis_client = MagicMock()
        mock_pipe = MagicMock()
        client.redis_client.pipeline.return_value = mock_pipe
        mock_pipe.execute.side_effect = Exception("Redis down")

        job = Job(job_id="test-fail", text="will fail")
        result = client.enqueue_job(job)
        assert result is False

    @patch("shared.queue_client.redis.Redis")
    def test_redis_unavailable_at_init(self, mock_redis):
        from shared.queue_client import QueueClient

        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.side_effect = Exception("Connection refused")
        mock_redis.return_value = mock_redis_instance

        client = QueueClient()
        assert client.redis_client is not None
