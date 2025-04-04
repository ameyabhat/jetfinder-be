import pika
import json
from typing import Callable, Dict, Any
import os
import time
import logging

class RabbitMQClient:
    def __init__(self, max_retries=5, retry_delay=5):
        self.connection = None
        self.channel = None
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.connect()
    
    def connect(self):
        """Establish connection to RabbitMQ with retry logic"""
        retries = 0
        while retries < self.max_retries:
            try:
                credentials = pika.PlainCredentials(
                    username=os.getenv('RABBITMQ_USER', 'guest'),
                    password=os.getenv('RABBITMQ_PASSWORD', 'guest')
                )
                parameters = pika.ConnectionParameters(
                    host=os.getenv('RABBITMQ_HOST', 'localhost'),
                    port=int(os.getenv('RABBITMQ_PORT', 5672)),
                    credentials=credentials,
                    heartbeat=30,  # Add heartbeat to detect connection issues
                    connection_attempts=3,
                    retry_delay=5
                )
                self.connection = pika.BlockingConnection(parameters)
                self.channel = self.connection.channel()
                logging.info("Successfully connected to RabbitMQ")
                return
            except Exception as e:
                retries += 1
                logging.error(f"Failed to connect to RabbitMQ (attempt {retries}/{self.max_retries}): {str(e)}")
                if retries < self.max_retries:
                    time.sleep(self.retry_delay * (2 ** (retries - 1)))
                else:
                    logging.error("Max retries reached. Could not connect to RabbitMQ.")
                    raise
    
    def ensure_connection(self):
        """Ensure the connection is active, reconnect if necessary"""
        if self.connection is None or self.connection.is_closed:
            logging.warning("RabbitMQ connection is closed. Attempting to reconnect...")
            self.connect()
    
    def consume_messages(self, queue_name: str, callback: Callable[[Dict[str, Any]], None]):
        """Start consuming messages from the specified queue"""
        self.ensure_connection()
        self.channel.queue_declare(queue=queue_name)
        self.channel.basic_consume(
            queue=queue_name,
            on_message_callback=lambda ch, method, properties, body: callback(json.loads(body)),
            auto_ack=True
        )
        try:
            self.channel.start_consuming()
        except pika.exceptions.AMQPConnectionError:
            logging.error("AMQP connection error. Attempting to reconnect...")
            self.connect()
            # Retry consuming
            self.consume_messages(queue_name, callback)
    
    def close(self):
        """Close the RabbitMQ connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close() 