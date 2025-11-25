import asyncio
import json
from typing import Awaitable, Callable, Iterable

import aio_pika

EXCHANGE_NAME = "library.events"
DEFAULT_ROUTING_KEY = "library.event"


async def publish_event(
    amqp_url: str,
    event_type: str,
    payload: dict,
    routing_key: str | None = None,
) -> None:
    """Publish an event to the shared topic exchange."""
    connection = await aio_pika.connect_robust(amqp_url)
    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
        )
        message = aio_pika.Message(
            body=json.dumps({"type": event_type, "payload": payload}).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await exchange.publish(message, routing_key or routing_key_from(event_type))


def routing_key_from(event_type: str) -> str:
    return event_type.replace("_", ".")


async def consume_events(
    amqp_url: str,
    queue_name: str,
    binding_keys: Iterable[str],
    handler: Callable[[dict], Awaitable[None]],
) -> None:
    """Continuously consume events and dispatch them to the handler."""
    connection = await aio_pika.connect_robust(amqp_url)
    channel = await connection.channel()
    exchange = await channel.declare_exchange(
        EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
    )
    queue = await channel.declare_queue(queue_name, durable=True)
    for binding_key in binding_keys:
        await queue.bind(exchange, routing_key=binding_key)

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            async with message.process():
                data = json.loads(message.body)
                await handler(data)


def start_consumer_background(task: Awaitable[None]) -> None:
    """Helper to run consumers in background threads."""
    loop = asyncio.get_event_loop()
    loop.create_task(task)


