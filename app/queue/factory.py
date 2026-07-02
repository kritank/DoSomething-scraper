from app.core.config import settings
from app.queue.base import QueueBackend

_queue_instance: QueueBackend | None = None

def get_queue() -> QueueBackend:
    """Return the configured queue backend instance."""
    global _queue_instance
    if _queue_instance is None:
        if settings.is_redis_queue:
            from app.queue.redis_queue import RedisQueueBackend
            _queue_instance = RedisQueueBackend()
        elif settings.is_sqs_queue:
            from app.queue.sqs_queue import SQSQueueBackend
            _queue_instance = SQSQueueBackend()
        else:
            raise ValueError(f"Unknown QUEUE_BACKEND: {settings.QUEUE_BACKEND}")
    return _queue_instance
