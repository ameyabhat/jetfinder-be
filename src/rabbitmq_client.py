import pika
import json
from typing import Callable, Dict, Any
import os

class RabbitMQClient:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.connect()
    
    def connect(self):
        """Establish connection to RabbitMQ"""
        credentials = pika.PlainCredentials(
            username=os.getenv('RABBITMQ_USER', 'guest'),
            password=os.getenv('RABBITMQ_PASSWORD', 'guest')
        )
        parameters = pika.ConnectionParameters(
            host=os.getenv('RABBITMQ_HOST', 'localhost'),
            port=int(os.getenv('RABBITMQ_PORT', 5672)),
            credentials=credentials
        )
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
    
    def consume_messages(self, queue_name: str, callback: Callable[[Dict[str, Any]], None]):
        """Start consuming messages from the specified queue"""
        self.channel.queue_declare(queue=queue_name)
        self.channel.basic_consume(
            queue=queue_name,
            on_message_callback=lambda ch, method, properties, body: callback(json.loads(body)),
            auto_ack=True
        )
        self.channel.start_consuming()
    
    def close(self):
        """Close the RabbitMQ connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close() 