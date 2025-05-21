import pprint
from typing import Dict, Any, Union


from contracts import FlightUpdateRequest
from tools.flight_finder import FlightFinderClient
from rabbitmq_client import RabbitMQClient
from email_processor import EmailProcessor
from postgres_client import PostgresClient

import logging
import traceback

class SearchOrchestrator:
	"""
	This class is responsible for orchestrating the search for vendor emails
	"""
	FlightPlanError = "FlightPlanError"
	NoVendorEmailsFound = "NoVendorEmailsFound"
	UnknownError = "UnknownError"

	def __init__(
		self,
		rabbitmq_client: RabbitMQClient,
		email_processor: EmailProcessor,
		flight_finder: FlightFinderClient,
		postgres_client: PostgresClient
	):
		self.rabbitmq_client = rabbitmq_client
		self.email_processor = email_processor
		self.flight_finder = flight_finder
		self.postgres_client = postgres_client
	
	def process_email_external(self, message):
		try:
			self.process_email(message)
		except Exception as e:
			logging.error(f"Error processing email: {e}")
			self.rabbitmq_client.send_error_message(
				queues= [self.rabbitmq_client.InternalErrorQueue, self.rabbitmq_client.ManualInterventionQueue],
				message=message,
				error_type=self.UnknownError, 
				**{ "error": str(e), "stacktrace": traceback.format_exc() }
			)
		


	def update_flight_search(self, request: FlightUpdateRequest) -> Union[Dict[str, Any],  str]:
		"""
		Recompute the flight plan for a given response
		"""
		#  What does this endpoint need to do?
		#  I should accept an email_id, user_id, plane_size, search_radius, number of passengers
		# Why don't I store the contents of the analysis in the database - then I can just look up the origin, number of passengers, 
		vendor_response = self.postgres_client.get_vendor_response_by_user_and_email(request.user_id, request.message_id)

		if not vendor_response:
			logging.error(f"No charter email matching this id was found for user {request.user_id} and email {request.message_id}")
			return self.UnknownError

		analysis = vendor_response.get('emailAnalysis')

		if not analysis:
			logging.error(f"No analysis found for user {request.user_id} and email {request.message_id}")
			return self.UnknownError

		flights = analysis.get('flights')

		if not flights:
			logging.error(f"malformed analysis for user {request.user_id} and email {request.message_id}")
			return self.UnknownError

		flight_origin = flights[0].get('origin')

		num_passengers = request.number_of_passengers or flights[0].get('passengers')

		aircraft_size = request.plane_size or flights[0].get('aircraft_size')

		radius = request.search_radius or 0


		print(flight_origin, num_passengers, [aircraft_size], radius)

		vendor_emails = self.flight_finder.search(flight_origin, num_passengers, [aircraft_size], radius)

		if len(vendor_emails) == 0:
			logging.error(f"No vendor emails found for user {request.user_id} and email {request.message_id}")
			return self.NoVendorEmailsFound
		
		pprint.pprint(flights)
		
		updated_flights = [{
			"origin": f.get('origin'),
			"destination": f.get('destination'),
			"travel_date": f.get('travel_date'),
			"passengers": num_passengers or f.get('passengers'),
			"aircraft_size": aircraft_size or f.get('aircraft_size')
		} for f in flights]

		updated_analysis = {
			"user_info": analysis.get('user_info'),
			"flights": updated_flights
		}

		email = self.email_processor.build_email(updated_analysis)

		self.postgres_client.update_vendor_response(
			user_id=request.user_id,
			email_id=request.message_id,
			vendor_emails=vendor_emails,
			email_analysis=updated_analysis,
			generated_body=email["body"],
			subject=email["subject"],
			radius=radius,
			plane_size=aircraft_size,
			number_of_passengers=num_passengers
		)

		response = self.postgres_client.get_vendor_response_by_user_and_email(request.user_id, request.message_id)

		if not response:
			logging.error(f"No vendor response found for user {request.user_id} and email {request.message_id} after response")
			return self.UnknownError
			

		return response


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
			#  This is so we can investigate the error later

			# This is so our frontend can show the user the error, and let them manually intervene
			self.rabbitmq_client.send_error_message(
				queues= [self.rabbitmq_client.InternalErrorQueue, self.rabbitmq_client.ManualInterventionQueue],
				message=message,
				error_type=self.FlightPlanError,
			)

			print("Invalid flight responses - llm needs to get better at handling these")
			return

		# This is only finding the vendor emails for the first flight
		starting_flight = analysis["flights"][0]

		logging.info("Searching for vendor emails ...")

		radius = 0
		max_radius = 250
		radius_increment = 50
		vendor_emails = []

		while len(vendor_emails) == 0 and radius <= max_radius:
			logging.info(f"Searching for vendor emails with radius {radius}...")
			vendor_emails = self.flight_finder.search(
				starting_flight["origin"], 
				starting_flight["passengers"], 
				[starting_flight["aircraft_size"]],
				radius=radius
			)
			
			if len(vendor_emails) == 0:
				radius += radius_increment
				logging.info(f"No results found, increasing radius to {radius}")

		if len(vendor_emails) == 0:
			response = { "error": self.NoVendorEmailsFound, "email_id": message.get('email_id'), "message": message }

			self.rabbitmq_client.send_error_message(
				queues= [self.rabbitmq_client.ManualInterventionQueue],
				message=response,
				error_type=self.NoVendorEmailsFound
			)

			logging.info("No vendor emails found")

		logging.info("Building email ...")
		email = self.email_processor.build_email(analysis)

		self.postgres_client.write_vendor_response(
			user_email=message.get('user_email'),
			request_body=email_content,
			email_id=message.get('email_id'),
			vendor_emails=vendor_emails,
			generated_body=email["body"],
			subject=email["subject"],
			email_analysis=analysis,
			radius=0,
			plane_size=starting_flight["aircraft_size"],
			number_of_passengers=starting_flight["passengers"]
		)

		return vendor_emails
		# Construct and send the response email
		
	
	def consume_emails(self):
		"""Start processing emails from the queue"""
		self.rabbitmq_client.consume_messages(
			queue_name= self.rabbitmq_client.EmailQueue,
			callback=self.process_email_external
		) 