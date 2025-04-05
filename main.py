import json
import os
from dotenv import load_dotenv
from src.search_orchestrator import SearchOrchestrator
from src.rabbitmq_client import RabbitMQClient
from src.email_processor import EmailProcessor
from src.tools.flight_finder import FlightFinderClient
from pprint import pprint
import logging
def main():
	# Load environment variables
	load_dotenv()
	logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)

	# Initialize components
	rabbitmq_client = RabbitMQClient()
	email_processor = EmailProcessor()
	flight_finder = FlightFinderClient()
	
	# Initialize the email processor
	processor = SearchOrchestrator(
		rabbitmq_client=rabbitmq_client,
		email_processor=email_processor,
		flight_finder=flight_finder
	)
	
	v = {
		"email_id": "123",
		"content": "Eduardo Your Itinerary : KMIO | Miami Municipal Airport | Miami, US KLVS | Las Vegas Municipal Airport | Las Vegas, US | 2025-08-13 08:00 | PAX: 3 Aircraft Size: Piston Prop First Name: Eduardo Last Name: COsta Email: eduaarc@gmail.com Phone - (Reliable # for time sensitive travel): +5541 State: FL How many hours do you fly privately each year?: 0-10 hours Firm trip or General Inquiry: Looking for general info on a route I'm interested in &nbsp; Thank you for Choosing Flight Finder Exclusive to handle your private charter needs. We are here to get you wheels up to your choice destination as well as to answer all flight related questions pertaining to cost or aircraft. Do not hesitate to ask any questions!&nbsp;&nbsp; Reach our 24/7 Advisors at 781-424-4597",
		"thread_id": "123",
		"user_email": "test@test.com"
	}

	# Start processing emails
	processor.consume_emails()

if __name__ == "__main__":
	main() 