import json
import logging

from app.core.config import settings
from app.queue.base import ScrapeJobMessage

try:
    import boto3
except ImportError:
    boto3 = None

logger = logging.getLogger(__name__)


class SQSQueueBackend:
    """Amazon SQS async queue implementation for production."""

    def __init__(self) -> None:
        if not boto3:
            raise ImportError("boto3 is required for SQSQueueBackend")
            
        self.queue_url = settings.AWS_SQS_QUEUE_URL
        # Only pass explicit static credentials when both are set. Passing
        # aws_access_key_id="" (the unset default) overrides boto3's default
        # credential chain instead of falling through it, which breaks
        # EC2 instance-profile/IAM-role auth -- that path only works when
        # boto3 is left to discover credentials itself.
        credential_kwargs = {}
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            credential_kwargs = {
                "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
                "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
            }
        self.sqs = boto3.client(
            "sqs",
            region_name=settings.AWS_REGION,
            **credential_kwargs,
        )

    async def enqueue(self, message: ScrapeJobMessage) -> str:
        # Using run_in_executor since boto3 is synchronous, or we could use aiobotocore
        import asyncio
        loop = asyncio.get_running_loop()
        
        def _send():
            response = self.sqs.send_message(
                QueueUrl=self.queue_url,
                MessageBody=message.model_dump_json()
            )
            return response["MessageId"]
            
        return await loop.run_in_executor(None, _send)

    async def dequeue(self, batch_size: int = 1) -> list[tuple[str, ScrapeJobMessage]]:
        import asyncio
        loop = asyncio.get_running_loop()
        
        def _receive():
            response = self.sqs.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=min(batch_size, 10),  # SQS max is 10
                WaitTimeSeconds=5,
            )
            return response.get("Messages", [])
            
        messages = await loop.run_in_executor(None, _receive)
        
        results = []
        for msg in messages:
            try:
                receipt = msg["ReceiptHandle"]
                job_msg = ScrapeJobMessage.model_validate_json(msg["Body"])
                results.append((receipt, job_msg))
            except Exception as e:
                logger.error(f"Failed to parse SQS message: {e}")
                
        return results

    async def delete(self, receipt_handle: str) -> None:
        import asyncio
        loop = asyncio.get_running_loop()
        
        def _delete():
            self.sqs.delete_message(
                QueueUrl=self.queue_url,
                ReceiptHandle=receipt_handle
            )
            
        await loop.run_in_executor(None, _delete)

    async def queue_depth(self) -> int:
        import asyncio
        loop = asyncio.get_running_loop()

        def _get_attrs():
            response = self.sqs.get_queue_attributes(
                QueueUrl=self.queue_url,
                AttributeNames=["ApproximateNumberOfMessages"]
            )
            return int(response["Attributes"].get("ApproximateNumberOfMessages", 0))

        return await loop.run_in_executor(None, _get_attrs)

    async def dlq_depth(self) -> int:
        """Message count on the dead-letter queue -- jobs that exceeded
        maxReceiveCount (infra/sqs.tf) and got redriven there instead of
        endlessly retrying. No separate DLQ URL setting exists; its name is
        deterministic (Terraform: "${var.sqs_queue_name}-dlq"), so derive
        the URL from the main queue's rather than adding new config."""
        import asyncio
        loop = asyncio.get_running_loop()
        dlq_url = self.queue_url + "-dlq"

        def _get_attrs():
            response = self.sqs.get_queue_attributes(
                QueueUrl=dlq_url,
                AttributeNames=["ApproximateNumberOfMessages"]
            )
            return int(response["Attributes"].get("ApproximateNumberOfMessages", 0))

        return await loop.run_in_executor(None, _get_attrs)
