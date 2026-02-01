import json
import logging
from typing import Any, Callable, Optional
from kafka import KafkaProducer
from kafka.errors import KafkaError

logger = logging.getLogger(__name__)


class EventProducer:
    """
    Wrapper around KafkaProducer for the trading system.
    Handles serialization and error logging.
    """

    def __init__(
        self, bootstrap_servers: str = "localhost:29092", client_id: str = "trading-producer"
    ):
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            client_id=client_id,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            retries=3,
        )
        logger.info(f"Kafka Producer initialized: {client_id}")

    def send(self, topic: str, value: Any, key: Optional[str] = None):
        """
        Send a message to a Kafka topic.

        Args:
            topic: The topic name (e.g., 'market.tick')
            value: The data to send (must be JSON serializable)
            key: Optional partitioning key (e.g., symbol)
        """
        try:
            future = self.producer.send(topic, value=value, key=key)
            # Block for result to ensure delivery (optional, better for debugging)
            # record_metadata = future.get(timeout=10)

            # For high throughput, use async callback
            future.add_callback(self._on_success)
            future.add_errback(self._on_error)

        except KafkaError as e:
            logger.error(f"Failed to send message to {topic}: {e}")

    def _on_success(self, record_metadata):
        logger.debug(
            f"Message delivered to {record_metadata.topic} partition {record_metadata.partition} offset {record_metadata.offset}"
        )

    def _on_error(self, exc):
        logger.error(f"Message delivery failed: {exc}")

    def close(self):
        self.producer.close()
