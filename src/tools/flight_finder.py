from enum import Enum
import logging
import re
from typing import Optional, Dict, Any, Union, List
import requests
import os
from bs4 import BeautifulSoup
from functools import reduce

flatmap = lambda f, xs: reduce(lambda acc, x: acc + f(x), xs, [])

class FlightFinderClient:
	CookieCi = "ci_session"

	def __init__(self, base_url: Optional[str] = None):
		self.base_url = base_url or os.getenv('FLIGHT_FINDER_BASE_URL', '')
		self.ci_session = os.getenv('FLIGHT_FINDER_CI_SESSION')
		self.session = requests.Session()  
		# This is hardcoded for now, but we're going to need to get this from the login page
		# There's a captcha on the login page that we need to solve, i don't want to deal with that right now
		self.session.cookies.set(self.CookieCi, self.ci_session)

	def get_aircraft_size(self, aircraft_size: str) -> Optional[int]:
		print("aircraft_size", aircraft_size)
		jetSizes = {
			"Ultra Long Range": 20,
			"Heavy Jet": 1,
			"Super Midsize Jet": 11,
			"Midsize Jet": 9,
			"Light Jet": 8,
			"Very Light Jet": 14,
			"Turbo Prop": 12,
			"Piston Prop": 10
		}
		print(jetSizes.get(aircraft_size))

		if aircraft_size not in jetSizes:
			return None  # Default to largest size if unknown

		return jetSizes[aircraft_size]

	def search(self, airportCode: str, numPassengers: int, aircraft_sizes: List[str], radius: int = 0):
		logging.info("Searching for vendor emails with code: %s and pax: %s", airportCode, numPassengers)

		print(aircraft_sizes)
		size_nums = [size for size in map(self.get_aircraft_size, aircraft_sizes) if size is not None]

		if size_nums:
			self.search_results(airportCode, pax=numPassengers, flight_sizes=size_nums, radius=radius)
		else:
			self.search_results(airportCode, pax=numPassengers, radius=radius)

		# This call is only relevant to set the correct params on the cookie
		htmlResponse = self.search_results_ajax(start=0, length=30)['data']
		
		vendorIds = list(set(map(lambda x: int(x), (flatmap(self.parse_search_results, htmlResponse)))))

		vendorEmails = list(map(self.extract_mailto, map(self.get_vendor_details, vendorIds)))
		print("vendorEmails", htmlResponse)

		return vendorEmails

	def get_vendor_details(self, vendorId: int):
		url = f"{self.base_url}/pages_view/vendor_details"

		form_data =  {
			"id": vendorId
		}

		try:
			response = self.session.post(url, data=form_data)
			response.raise_for_status()
			return response.text
		except requests.exceptions.RequestException as e:
			raise Exception(f"Failed to make vendor details request: {str(e)}")
	
	def extract_mailto(self, html_text: str) -> str:
		soup = BeautifulSoup(html_text, 'html.parser')
		if mailto_link := soup.find('a', href=lambda x: x and x.startswith('mailto:')):
			return mailto_link['href'].replace('mailto:', '')
		
		return None

	def parse_search_results(self, html_list: list):
		return list(filter(lambda x: x is not None, [self.extract_vendor_id(element) for element in html_list]))

	def extract_vendor_id(self, html_element: str) -> str:
		if match := re.search(r'vendor_details\((\d+)\)', f"{html_element}"):
			return match.group(1)
		return None

	def search_results(
		self,
		code: str,
		capability: str = "PASSENGER",
		searchby: str = "AirportCode",
		radius: int = 0,
		pax: str = "Any",
		yom_min: Optional[str] = None,
		flight_sizes: Optional[List[int]] = None,
		rdtype: str = "Category",
		submit_user: str = "search"
	) -> str:
		"""
		Make a POST request to /search-results with form data
		
		Args:
			capability: Type of capability (default: PASSENGER)
			searchby: Search method (default: AirportCode)
			code: Airport code or search term
			radius: Search radius in miles (default: 250)
			pax: Passenger type (default: Any)
			yom_min: Year of manufacture minimum
			rdtype: Result type (default: Category)
			submit_user: Submit user identifier (default: Search)
			
		Returns:
			Dict containing the API response
		"""

		url = f"{self.base_url}/search-results"
		
		form_data = {
			"capability": capability,
			"searchby": searchby,
			"code": code,
			"radius": radius,
			"pax": pax,
			"rdtype": rdtype,
			"submit-user": submit_user
		}

		if flight_sizes:
			form_data["category[]"] = flight_sizes

		if yom_min:
			form_data["yom_min"] = yom_min
		
		try:
			response = self.session.post(url, data=form_data)
			print("response", response.text)
			response.raise_for_status()  # Raise an exception for bad status codes
			self.ci_cookie = response.cookies.get(self.CookieCi)
			return response.text

		except requests.exceptions.RequestException as e:
			raise Exception(f"Failed to make search request: {str(e)}")

	
	def search_results_ajax(
		self, 
		start: int = 0,
		length: int = 1,
	) -> Dict[str, Any]:
		"""
		Make a POST request to /search-results-ajax with DataTables parameters
		
		Args:
			draw: Counter for DataTables (default: 2)
			start: Starting record number (default: 0)
			length: Number of records to retrieve (default: 200)
			order_column: Column to sort by (default: 0)
			order_dir: Sort direction (default: "asc")
			search_value: Global search value (default: "")
			cookies: Optional dictionary or RequestsCookieJar of cookies to include in the request
			
		Returns:
			Dict containing the DataTables response
		"""
		url = f"{self.base_url}/search-results-ajax"
		
		# Construct the form data
		form_data = {
			"start": start,
			"length": length,
			"order[0][column]": 0,
			"order[0][dir]": "asc"
		}
		
	
		try:
			response = self.session.post(url, data=form_data)
			response.raise_for_status()
			return response.json()
		except requests.exceptions.RequestException as e:
			raise Exception(f"Failed to make AJAX search request: {str(e)}") 

	  
