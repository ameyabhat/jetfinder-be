from typing import Dict, Any, Optional, Union
from pprint import pprint

from app import FlightUpdateRequest
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
		vendor_response = self.postgres_client.get_vendor_response_by_user_and_email(request.user_email, request.message_id)

		if not vendor_response:
			logging.error(f"No charter email matching this id was found for user {request.user_email} and email {request.message_id}")
			return self.UnknownError

		analysis = vendor_response.get('emailAnalysis')
		if not analysis:
			logging.error(f"No analysis found for user {request.user_email} and email {request.message_id}")
			return self.UnknownError

		# Ok here's the plan:
		passengers = request.number_of_passengers

		flights = analysis.get('flights')

		if not flights:
			logging.error(f"malformed analysis for user {request.user_email} and email {request.message_id}")
			return self.UnknownError

		flight_origin = flights[0].get('origin')

		num_passengers = request.number_of_passengers or flights[0].get('passengers')

		aircraft_size = request.plane_size or flights[0].get('aircraft_size')

		radius = request.search_radius or 0


		vendor_emails = self.flight_finder.search(flight_origin, num_passengers, [aircraft_size], radius)

		if len(vendor_emails) == 0:
			logging.error(f"No vendor emails found for user {request.user_email} and email {request.message_id}")
			return self.NoVendorEmailsFound
		
		
		updated_flights = [{
			"origin": f.origin,
			"destination": f.destination,
			"travel_date": f.travel_date,
			"passengers": num_passengers or f.passengers,
			"aircraft_size": aircraft_size or f.aircraft_size
		} for f in flights]

		updated_analysis = {
			"user_info": analysis.get('user_info'),
			"flights": updated_flights
		}

		email = self.email_processor.build_email(updated_analysis)

		self.postgres_client.update_vendor_response(
			user_id=request.user_email,
			email_id=request.message_id,
			vendor_emails=vendor_emails,
			email_analysis=updated_analysis,
			generated_body=email["body"],
			subject=email["subject"],
			radius=radius,
			plane_size=aircraft_size,
			number_of_passengers=num_passengers
		)

		return {
			"vendor_emails": vendor_emails,
			"body": email["body"],
			"subject": email["subject"]
		}
	


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
		logging.info("Searching for vendor emails ...")
		vendor_emails = self.flight_finder.search(analysis["flights"][0]["origin"], analysis["flights"][0]["passengers"], analysis["flights"][0]["aircraft_size"])

		if len(vendor_emails) == 0:
			response = { "error": self.NoVendorEmailsFound, "email_id": message.get('email_id'), "message": message }

			self.rabbitmq_client.send_error_message(
				queues= [self.rabbitmq_client.ManualInterventionQueue],
				message=response,
				error_type=self.NoVendorEmailsFound
			)

			logging.info("No vendor emails found")
			return

		logging.info("Building email ...")
		email = self.email_processor.build_emil(analysis)

		self.postgres_client.write_vendor_response(
			user_email=message.get('user_email'),
			request_body=email_content,
			email_id=message.get('email_id'),
			vendor_emails=vendor_emails,
			generated_body=email["body"],
			subject=email["subject"],
			email_analysis=analysis,
			radius=0,
			plane_size=analysis["flights"][0]["aircraft_size"],
			number_of_passengers=analysis["flights"][0]["passengers"]
		)

		return vendor_emails
		# Construct and send the response email
		
	
	def consume_emails(self):
		"""Start processing emails from the queue"""
		self.rabbitmq_client.consume_messages(
			queue_name= self.rabbitmq_client.EmailQueue,
			callback=self.process_email_external
		) 