import json
import os
from openai import OpenAI
from typing import Dict, Any, List, Tuple
from datetime import datetime

class EmailProcessor:
	example_client_completion = """
	{{
		"is_charter_request": true,
		  "flights": [
			{{
				"origin": "KDFW",
				"destination": "KMSY",
				"departure_date": "2025-05-14 20:29 UTC",
				"pax": 3,
				"aircraft_size": "Piston Prop"
			}}, 
			{{
				"origin": "KMSY",
				"destination": "KDFW",
				"departure_date": "2025-05-17 20:30 UTC",
				"pax": 3,
				"aircraft_size": "Piston Prop"
			}}
		 ],
		 "user_info": {{
			"user_email": "<User Email>",
			"user_phone": "<User Phone Number>",
			"user_state": "TX",
			"user_first_name": "<User First Name>",
			"user_last_name": "<User Last Name>",
			"user_firm_trip": true,
			"user_frequent_flyer": false
		 }}
	}}
	"""
	
	example_client_completion_2 = """
	{{
		"is_charter_request": true,
		"flights": [
			{{
				"origin": "KFTY",
				"destination": "KJFK",
				"travel_date": "2025-08-08 10:30 UTC",
				"passengers": 4,
				"aircraft_size": "Unknown"
			}}
		],
		"user_info": {{
			"user_email": "<User Email>",
			"user_phone": "<User Phone Number>",
			"user_state": "NJ",
			"user_first_name": "<User First Name>",
			"user_last_name": "<User Last Name>"
		}}
	}}
	"""

	def __init__(self):
		api_key = os.getenv('OPENAI_API_KEY')
		if not api_key:
			raise ValueError("OPENAI_API_KEY environment variable is not set")
		self.client = OpenAI(api_key=api_key)
		
		
	def analyze_incoming_email(self, email_body: str) -> Dict[str, Any]:
		example_client_request_email = """
			<User First Name> Your Itinerary :
			KDFW | Dallas Fort Worth International Airport | Dallas-Fort Worth, US KMSY | Louis Armstrong New Orleans International Airport | New Orleans, US | 2025-05-14 20:29 | PAX: 3
			KMSY | Louis Armstrong New Orleans International Airport | New Orleans, US KDFW | Dallas Fort Worth International Airport | Dallas-Fort Worth, US | 2025-05-17 20:30 | PAX: 3
			Aircraft Size: Piston Prop 
			First Name: <User First Name>
			Last Name: <User Last Name>
			Email: <User Email> 
			Phone - (Reliable # for time sensitive travel): <User Phone Number>
			State: TX
			How many hours do you fly privately each year?: 0-10 hours
			Firm trip or General Inquiry: This trip is 100% Firm 
		"""
	
		example_client_request_email_2 = """
			<User First Name> Your Itinerary :
			  KFTY | Fulton County Airport Brown Field | Atlanta, US KJFK | John F Kennedy International Airport | New York, US | 2025-08-08 10:30 | PAX: 4
			  Aircraft Size: Not sure, please advise me
			  First Name: <User First Name>
			  Last Name: <User Last Name>
			  Email: <User Email>
			  Phone - (Reliable # for time sensitive travel): <User Phone Number>
			  State: NJ
			  How many hours do you fly privately each year?: 0-10 hours
			  Firm trip or General Inquiry: Looking for general info on a route I'm interested in
		"""
	
		prompt = f"""
		Analyze the following email and determine if it's a request for chartering a private jet.
		If it is, extract the following information:
		- Origin airport/city
		- Destination airport/city
		- Date of travel
		- Number of passengers
		- Any specific requirements

		Respond in JSON format with the following structure:
		{{
			"is_charter_request": boolean,
			"user_info": {{
				"user_email": string or null,
				"user_phone": string or null,
				"user_state": string or null,
				"user_first_name": string or null,
				"user_last_name": string or null,
			}}
			"flights": [
				{{
					"origin": string or null,
					"destination": string or null,
					"travel_date": string or null (the format MUST be YYYY-MM-DD HH:MM UTC),
					"passengers": number or null,
					"aircraft_size": string or null,
				}}
			],
		}}

		If you determine that the email is not a private jet charter request, respond with:
		{{
			"is_charter_request": false
		}}

		<examples>
		Here's an example of what a private jet charter request looks like:
		
		{example_client_request_email}

		Here's what I would expect the completion to be:

		{self.example_client_completion}

		Here's another example of what a private jet charter request looks like:

		{example_client_request_email_2}

		Here's what I would expect the completion to be:

		{self.example_client_completion_2}
		</examples>
		
		<content>
		{email_body}
		</content>
		"""
		
		response = self.client.chat.completions.create(
			model="gpt-4o-mini",
			messages=[
				{"role": "system", "content": "You are an AI assistant that analyzes emails for private jet charter requests."},
				{"role": "user", "content": prompt}
			],
			response_format={ "type": "json_object" }
		)
		
		try:
			return json.loads(response.choices[0].message.content)
		except Exception as e:
			print(e)

	def build_email(self, flight_info: Dict[str, Any]) -> Dict[str, Any]:
		routes, dates, body_dates = self.parse_flight_dates(flight_info["flights"])

		subject = self.build_subject(routes, dates, flight_info["flights"][0]["aircraft_size"])
		#  TODO: This is just using the first flight in the list - we need to be smarter about this
		body = self.build_body(routes, body_dates, flight_info["flights"][0]["passengers"])

		return {
			"subject": subject,
			"body": body
		}

	def parse_flight_dates(self, flights: List[Dict[str, Any]]) -> List[Tuple[str, any]]:
		print([fl["travel_date"] for fl in flights])
		parsed_flights = list(map(lambda flight: (
			flight["origin"], 
			flight["destination"], 
			datetime.strptime(flight["travel_date"], "%Y-%m-%d %H:%M UTC").date()
		), flights))

		fmt_string = '%m/%d/%Y'
		body_fmt_string = '%m/%d/%Y %H:%M'

		route = f"{parsed_flights[0][0]} - {parsed_flights[0][1]}"
		dates = f"{parsed_flights[0][2].strftime(fmt_string)}"
		body_dates = f"{parsed_flights[0][2].strftime(body_fmt_string)}"

		for i in range(1, len(parsed_flights)):
			route += f" - {parsed_flights[i][0]}"
			dates += f" - {parsed_flights[i][2].strftime(fmt_string)}"
			body_dates += f" - {parsed_flights[i][2].strftime(body_fmt_string)}"
		
		return (route, dates, body_dates)
			

	def validate_flight_plan(self, flight_info: Dict[str, Any]) -> bool:
		last_date = None
		last_destination = None
		if len(flight_info["flights"]) == 0:
			return False

		if len(flight_info["flights"]) == 1:
			return True
		
		for flight in flight_info["flights"]:
			if last_date is None:
				last_date = flight["travel_date"]
			else:
				if flight["travel_date"] > last_date:
					last_date = flight["travel_date"]
				else: 
					return False
				
			if last_destination is None:
				last_destination = flight["destination"]
			else:
				if flight["origin"] != last_destination:
					return False
			
		return True
		

	def build_subject(self, route, dates, size) -> str:
		return f"{route} | {dates} | {size}"

	def build_body(self, route, dates, passengers) -> str:
		return f"Hello team, can you please provide a quote for {route} {dates}? {passengers} PAX.  Thank you!"
