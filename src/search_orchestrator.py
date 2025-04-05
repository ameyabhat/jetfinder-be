import json
from typing import Dict, Any


from .tools.flight_finder import FlightFinderClient
from .rabbitmq_client import RabbitMQClient
from .email_processor import EmailProcessor

class SearchOrchestrator:
    def __init__(
        self,
        rabbitmq_client: RabbitMQClient,
        email_processor: EmailProcessor,
		flight_finder: FlightFinderClient
    ):
        self.rabbitmq_client = rabbitmq_client
        self.email_processor = email_processor
        self.flight_finder = flight_finder
    
    def process_email_external(self, message):
        try:
            self.process_email(message)
        except Exception as e:
            print(message, e)
            return

    def process_email(self, message):
        """Process a single email"""
        # Extract email content
        """
        Here's the message structure
        {
            "email_id": string,
            "content": string,
            "thread_id": string,
            "user_email": string
        }
        """

        email_content = message.get('content', '')

        if email_content == "":
            print("No email content")
            return
        
        # Analyze the email using LLM
        analysis = self.email_processor.analyze_incoming_email(email_content)

        if not analysis.get('is_charter_request'):
            return

        if not self.email_processor.validate_flight_dates(analysis):           
            print("Invalid flight responses - llm needs to get better at handling these")
            return

        # If it's not a jet charter request, don't process it
        details = analysis["details"]

		# This is only finding the vendor emails for the first flight
        vendor_emails = self.flight_finder.search(details["origin"], int(details["flights"][0]["passengers"]))
        email = self.email_processor.build_email(details)

        response = {
            "vendor_emails": vendor_emails,
            "body": email["body"],
            "subject": email["subject"]
        }

        self.email_processor.send_email(email)
        return vendor_emails
        # Construct and send the response email
        
    
    def consume_emails(self):
        """Start processing emails from the queue"""
        self.rabbitmq_client.consume_messages(
            queue_name='email_queue',
            callback=self.process_email_external
        ) 