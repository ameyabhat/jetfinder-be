import json
from typing import Dict, Any
from pprint import pprint

from .tools.flight_finder import FlightFinderClient
from .rabbitmq_client import RabbitMQClient
from .email_processor import EmailProcessor

import logging

class SearchOrchestrator:
    """
    This class is responsible for orchestrating the search for vendor emails
    """
    FlightPlanError = "FlightPlanError"
    NoVendorEmailsFound = "NoVendorEmailsFound"

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
        self.process_email(message)
        

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
            logging.info("No email content")
            return
        
        # Analyze the email using LLM
        logging.info("Analyzing email ...")
        analysis = self.email_processor.analyze_incoming_email(email_content)

        # If it's not a jet charter request, don't process it
        if not analysis.get('is_charter_request'):
            logging.info("Not a charter request")
            return

        logging.info("Validating flight dates ...")
        if not self.email_processor.validate_flight_plan(analysis):           
            response = { "error": self.FlightPlanError, "email_id": message.get('email_id'), "message": message }

			#  This is so we can investigate the error later
            self.rabbitmq_client.send_message(
                queue_name= self.rabbitmq_client.InternalErrorQueue,
                message=response
            )

            # This is so our frontend can show the user the error, and let them manually intervene
            self.rabbitmq_client.send_message(
                queue_name= self.rabbitmq_client.ManualInterventionQueue,
                message=response
            )

            print("Invalid flight responses - llm needs to get better at handling these")
            return

		# This is only finding the vendor emails for the first flight
        logging.info("Searching for vendor emails ...")
        vendor_emails = self.flight_finder.search(analysis["flights"][0]["origin"], analysis["flights"][0]["passengers"])

        if len(vendor_emails) == 0:
            response = { "error": self.NoVendorEmailsFound, "email_id": message.get('email_id'), "message": message }

            self.rabbitmq_client.send_message(
                queue_name= self.rabbitmq_client.ManualInterventionQueue,
                message=response
            )

            logging.info("No vendor emails found")
            return

        logging.info("Building email ...")
        email = self.email_processor.build_email(analysis)

        response = {
            "vendor_emails": vendor_emails,
            "body": email["body"],
            "subject": email["subject"]
        }

        pprint (response)
        
        self.rabbitmq_client.send_message(
            queue_name= self.rabbitmq_client.VendorOutreachQueue,
            message=response
        )

        return vendor_emails
        # Construct and send the response email
        
    
    def consume_emails(self):
        """Start processing emails from the queue"""
        self.rabbitmq_client.consume_messages(
            queue_name= self.rabbitmq_client.EmailQueue,
            callback=self.process_email_external
        ) 