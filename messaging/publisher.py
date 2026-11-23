
import json
import os

import pika

RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL",
    "amqp://lending:lending_dev_password@localhost:5672/%2F",
)

EXCHANGE = "equipment.events"


def publish_event(event_type, equipment):
    connection = pika.BlockingConnection(
        pika.URLParameters(RABBITMQ_URL)
    )

    try:
        channel = connection.channel()

        channel.exchange_declare(
            exchange=EXCHANGE,
            exchange_type="topic",
            durable=True,
        )

        channel.confirm_delivery()

        message = {
            "event_type": event_type,
            "equipment_id": equipment["id"],
            "name": equipment["name"],
            "description": equipment["description"],
            "status": equipment.get("status", "active"),
        }

        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key=event_type,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
        )

    finally:
        connection.close()
