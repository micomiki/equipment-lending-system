"""Consume equipment events into a read-model in the shared SQLite database."""

import json
import logging
import os
import sqlite3
import time

import pika

from services.loan_service.database import db, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL", "amqp://lending:lending_dev_password@rabbitmq:5672/%2F"
)
EXCHANGE = "equipment.events"
QUEUE = "loan.equipment.cache"


def prepare_database():
    init_db()
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS equipment_cache (
                equipment_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active'
            )"""
        )


def handle_message(channel, method, properties, body):
    try:
        event = json.loads(body)
        event_type = event["event_type"]
        if event_type not in {"equipment.created", "equipment.updated", "equipment.deleted"}:
            logger.warning("Ignoring unknown event type: %s", event_type)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        equipment_id = int(event["equipment_id"])
        status = "deleted" if event_type == "equipment.deleted" else event.get("status", "active")
        with db() as conn:
            conn.execute(
                """INSERT INTO equipment_cache (equipment_id, name, description, status)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(equipment_id) DO UPDATE SET
                       name=excluded.name,
                       description=excluded.description,
                       status=excluded.status""",
                (equipment_id, event.get("name", ""), event.get("description", ""), status),
            )
        channel.basic_ack(delivery_tag=method.delivery_tag)
        logger.info("Processed %s for equipment %s", event_type, equipment_id)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        logger.exception("Invalid message; rejecting")
        channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
    except sqlite3.Error:
        logger.exception("Database error; requeueing")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        time.sleep(1)


def run():
    prepare_database()
    while True:
        try:
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            channel = connection.channel()
            channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
            channel.queue_declare(queue=QUEUE, durable=True)
            channel.queue_bind(queue=QUEUE, exchange=EXCHANGE, routing_key="equipment.*")
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=QUEUE, on_message_callback=handle_message)
            logger.info("Listening for equipment events")
            channel.start_consuming()
        except (pika.exceptions.AMQPError, OSError):
            logger.exception("RabbitMQ connection lost; retrying")
            time.sleep(3)


if __name__ == "__main__":
    run()
