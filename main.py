from dotenv import load_dotenv
from src.search_orchestrator import SearchOrchestrator
from src.rabbitmq_client import RabbitMQClient
from src.email_processor import EmailProcessor
from src.tools.flight_finder import FlightFinderClient
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

	# Start processing emails
	processor.consume_emails()

if __name__ == "__main__":
	main() 