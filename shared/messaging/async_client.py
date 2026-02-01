import asyncio
import json
import logging
from typing import Optional, Callable, List, Type, TypeVar
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class AsyncEventProducer:
    def __init__(self, bootstrap_servers: str, client_id: str):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            client_id=client_id,
            value_serializer=lambda v: v.model_dump_json().encode("utf-8")
            if isinstance(v, BaseModel)
            else json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
        )

    async def start(self):
        await self.producer.start()
        logger.info("Async Producer started")

    async def stop(self):
        await self.producer.stop()

    async def send(self, topic: str, event: BaseModel, key: Optional[str] = None):
        """Send Pydantic model to Kafka."""
        try:
            await self.producer.send_and_wait(topic, value=event, key=key)
        except Exception as e:
            logger.error(f"Failed to send to {topic}: {e}")


class AsyncEventConsumer:
    def __init__(
        self,
        topics: List[str],
        group_id: str,
        bootstrap_servers: str,
        event_type: Type[T] = None,
    ):
        self.consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset="latest",
            enable_auto_commit=True,
        )
        self.event_type = event_type

    async def start(self):
        await self.consumer.start()
        logger.info("Async Consumer started")

    async def stop(self):
        await self.consumer.stop()

    async def consume(self, handler: Callable[[T], None]):
        """Consume loop yielding Pydantic models."""
        try:
            async for msg in self.consumer:
                try:
                    data = json.loads(msg.value)
                    # Validate if schema provided
                    if self.event_type:
                        event = self.event_type(**data)
                        if asyncio.iscoroutinefunction(handler):
                            await handler(event)
                        else:
                            handler(event)
                    else:
                        # Raw dict fallback
                        if asyncio.iscoroutinefunction(handler):
                            await handler(data)
                        else:
                            handler(data)

                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        finally:
            await self.stop()
