import json
import logging
from typing import Callable, List, Optional
from kafka import KafkaConsumer
from kafka.errors import KafkaError

logger = logging.getLogger(__name__)


class EventConsumer:
    """
    Wrapper around KafkaConsumer for the trading system.
    Handles deserialization and processing loops.
    """

    def __init__(
        self,
        topics: List[str],
        group_id: str,
        bootstrap_servers: str = "localhost:29092",
        auto_offset_reset: str = "latest",
    ):
        self.consumer = KafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset=auto_offset_reset,
            value_deserializer=lambda x: json.loads(x.decode("utf-8")),
            key_deserializer=lambda x: x.decode("utf-8") if x else None,
            enable_auto_commit=True,
        )
        self.running = True
        logger.info(f"Kafka Consumer initialized for topics {topics} group {group_id}")

    def consume(self, handler: Callable[[dict], None]):
        """
        Start consuming messages and pass them to the handler function.

        Args:
            handler: A function that takes a message dictionary as input.
        """
        try:
            for message in self.consumer:
                if not self.running:
                    break

                try:
                    handler(message.value)
                except Exception as e:
                    logger.error(f"Error processing message from {message.topic}: {e}")

        except KafkaError as e:
            logger.error(f"Kafka consumption error: {e}")
        finally:
            self.close()

    def stop(self):
        """Stop the consumption loop."""
        self.running = False

    def close(self):
        self.consumer.close()
