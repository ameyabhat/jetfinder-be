import os
from dotenv import load_dotenv
from src.email_processor import EmailProcessor
from src.rabbitmq_client import RabbitMQClient
from src.llm_analyzer import LLMAnalyzer
from src.email_sender import EmailSender
from src.tools.flight_finder import FlightFinderClient

def main():
    # Load environment variables
    load_dotenv()
    
    # Initialize components
    rabbitmq_client = RabbitMQClient()
    llm_analyzer = LLMAnalyzer()
    email_sender = EmailSender()
    flight_finder = FlightFinderClient()
    
    # Initialize the email processor
    processor = EmailProcessor(
        rabbitmq_client=rabbitmq_client,
        llm_analyzer=llm_analyzer,
        email_sender=email_sender
    )
    
    
    print(flight_finder.search("LAX"))
    
    # Start processing emails
    # processor.consume_emails()


if __name__ == "__main__":
    main() 