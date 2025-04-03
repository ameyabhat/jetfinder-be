import json
from typing import Dict, Any

from tools.flight_finder import FlightFinderClient
from .rabbitmq_client import RabbitMQClient
from .llm_analyzer import LLMAnalyzer

class EmailProcessor:
    def __init__(
        self,
        rabbitmq_client: RabbitMQClient,
        llm_analyzer: LLMAnalyzer,
        email_sender: EmailSender,
		flight_finder: FlightFinderClient
    ):
        self.rabbitmq_client = rabbitmq_client
        self.llm_analyzer = llm_analyzer
        self.email_sender = email_sender
        self.flight_finder = flight_finder
    
    def process_email(self, email_data: str):
        """Process a single email"""
        # Extract email content
        email_content = email_data.get('content', '')
        
        # Analyze the email using LLM
        analysis_result = self.llm_analyzer.analyze_email(email_content)
        analysis = json.loads(analysis_result)
        
        # If it's a jet charter request, process it
        if analysis.get('is_jet_charter_request'):
            # TODO: Call external API to gather email addresses
            # This is where you'll implement your API call
            email_addresses = []  # Replace with actual API call
            
            # Construct and send the response email
            self.email_sender.send_email(
                to=email_data.get('from'),
                subject="Re: Private Jet Charter Request",
                content=self._construct_response_email(analysis['details']),
                bcc=email_addresses
            )
    
    def _construct_response_email(self, details: Dict[str, Any]) -> str:
        """Construct the response email content"""
        return f"""
        Thank you for your private jet charter request. We have received your request with the following details:
        
        Origin: {details.get('origin', 'Not specified')}
        Destination: {details.get('destination', 'Not specified')}
        Travel Date: {details.get('travel_date', 'Not specified')}
        Number of Passengers: {details.get('passengers', 'Not specified')}
        Special Requirements: {details.get('requirements', 'None')}
        
        Our team will review your request and get back to you shortly with available options.
        
        Best regards,
        Your Private Jet Charter Team
        """
    
    def consume_emails(self):
        """Start processing emails from the queue"""
        self.rabbitmq_client.consume_messages(
            queue_name='email_queue',
            callback=self.process_email
        ) 