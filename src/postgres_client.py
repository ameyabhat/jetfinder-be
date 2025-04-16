import os
from datetime import datetime
from contextlib import contextmanager
from typing import Any, Generator, List, Optional, Dict
from dotenv import load_dotenv
from psycopg import Cursor, Connection
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
import logging

class PostgresClient:
	def __init__(self):
		load_dotenv()
		if os.getenv('DATABASE_URL') is not None:
			conninfo = os.getenv('DATABASE_URL')
		else: 
			conninfo = f"dbname={os.getenv('DB_NAME')} user={os.getenv('DB_USER')} password={os.getenv('DB_PASSWORD')} host={os.getenv('DB_HOST')} port={os.getenv('DB_PORT')}"
		# Configure the connection pool with specific settings
		self.pool = ConnectionPool(
			conninfo,
			min_size=1,  # Minimum number of connections to maintain
			max_size=10,  # Maximum number of connections in the pool
			timeout=30,   # Connection timeout in seconds
			check=lambda conn: conn.execute("SELECT 1")  # Health check query
		)

	@contextmanager
	def get_cursor(self, commit=False):
		conn = None
		try:
			conn = self.pool.getconn()
			cursor = conn.cursor(row_factory=dict_row)
			try:
				yield cursor
				if commit:
					conn.commit()
			except Exception as e:
				if conn:
					conn.rollback()
				logging.error(f"Database error: {str(e)}")
				raise
			finally:
				conn.rollback()
				cursor.close()
		finally:
			if conn:
				self.pool.putconn(conn)

	@contextmanager
	def get_connection(self) -> Generator[Connection, None, None]:
		conn = None
		try:
			conn = self.pool.getconn()
			yield conn
		except Exception as e:
			logging.error(f"Connection error: {str(e)}")
			raise
		finally:
			if conn:
				self.pool.putconn(conn)

	def get_user_id_by_email(self, email: str) -> Optional[str]:
		"""
		Get a user's ID by their email address.
		
		Args:
			email: The email address to look up
			
		Returns:
			Optional[str]: The user ID if found, None otherwise
		"""
		try:
			with self.get_cursor() as cur:
				cur.execute("""
					SELECT id FROM "User" WHERE email = %s;
				""", (email,))
				
				result = cur.fetchone()
				return result['id'] if result else None
		except Exception as e:
			logging.error(f"Error getting user ID by email: {str(e)}")
			raise

	def write_vendor_response(
		self,
		user_email: str,
		request_body: Optional[str],
		email_id: str,
		vendor_emails: Optional[List[str]],
		generated_body: Optional[str],
		subject: Optional[str],
		email_analysis: Dict[str, Any],
		radius: int,
		plane_size: str,
		number_of_passengers: int
	) -> str:
		"""
		Write a new vendor response to the database.
		
		Args:
			email_id: The ID of the email this response is associated with
			vendor_emails: List of vendor email addresses
			generated_body: The generated body text of the response
			subject: The subject line of the response
		Returns:
			str: The ID of the newly created vendor response
		"""
		try:
			# First get the user ID
			user_id = self.get_user_id_by_email(user_email)
			if not user_id:
				raise ValueError(f"User with email {user_email} not found")
				
			with self.get_cursor(commit=True) as cur:
				cur.execute("""
					INSERT INTO "VendorResponse" (
						"userId",
						"emailId", 
						"vendorEmails", 
						"requestBody", 
						"responseBody", 
						"responseSubject",
						"updatedAt",
						"emailAnalysis",
						"radius",
						"planeSize",
						"numPassengers"
					) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
					RETURNING id;
				""", (
					user_id,
					email_id,
					vendor_emails,
					request_body,
					generated_body,
					subject,
					datetime.now(),
					Jsonb(email_analysis),
					radius,
					plane_size,
					number_of_passengers
				))
				
				result = cur.fetchone()
				return result['id']  # Using dict_row, so we can access by column name
		except Exception as e:
			logging.error(f"Error writing vendor response: {str(e)}")
			raise

	def get_vendor_responses_for_user(
		self,
		user_id: str,
		page: int = 1,
		page_size: int = 10,
		sort_order: str = 'desc'
	) -> Dict[str, Any]:
		"""
		Get paginated vendor responses for a given user ID.
		
		Args:
			user_id: The ID of the user whose responses to fetch.
			page: The page number to retrieve (1-indexed).
			page_size: The number of responses per page.
			sort_order: The order to sort responses ('asc' or 'desc').
		
		Returns:
			A dictionary containing the list of responses, total count, page number, and total pages.
		"""
		try:
			with self.get_cursor() as cur:
				# Count total responses for the user
				cur.execute('''
					SELECT COUNT(*) FROM "VendorResponse" WHERE "userId" = %s;
				''', (user_id,))
				total_count_result = cur.fetchone()
				total_count = total_count_result['count'] if total_count_result else 0

				if total_count == 0:
					return {"responses": [], "total": 0, "page": page, "total_pages": 0}

				# Calculate offset and total pages
				offset = (page - 1) * page_size
				total_pages = (total_count + page_size - 1) // page_size

				# Validate page number
				if page < 1 or page > total_pages:
					raise ValueError("Invalid page number")

				# Determine sort direction safely
				if sort_order.lower() == 'asc':
					sort_clause = 'ORDER BY "createdAt" ASC'
				else:
					sort_clause = 'ORDER BY "createdAt" DESC' # Default to DESC

				# Fetch paginated responses using safe parameterization
				# Build the query string safely, ensuring %s placeholders are literal
				query = (
					'SELECT * FROM "VendorResponse" '
					'WHERE "userId" = %s '
					+ sort_clause + # Inject the validated sort clause
					' LIMIT %s OFFSET %s;'
				)
				
				cur.execute(query, (user_id, page_size, offset))
				responses = cur.fetchall()

				return {
					"responses": responses,
					"total": total_count,
					"page": page,
					"total_pages": total_pages
				}
		except ValueError as ve:
			logging.warning(f"Invalid request parameters: {str(ve)}")
			# Return an empty list for invalid page numbers, consistent with API expectations
			return {"responses": [], "total": total_count if 'total_count' in locals() else 0, "page": page, "total_pages": total_pages if 'total_pages' in locals() else 0}
		except Exception as e:
			logging.error(f"Error getting paginated vendor responses for user {user_id}: {str(e)}")
			raise

	def get_vendor_response_by_user_and_email(self, user_id: str, email_id: str) -> Optional[Dict]:
		"""
		Get a single vendor response for a given user ID and email ID.
		
		Args:
			user_id: The ID of the user (as a string)
			email_id: The email ID associated with the vendor response
		
		Returns:
			A dictionary representing the vendor response, or None if not found
		"""
		try:
			with self.get_cursor() as cur:
				cur.execute('''
					SELECT * FROM "VendorResponse"
					WHERE "userId" = %s AND "emailId" = %s
					LIMIT 1;
				''', (user_id, email_id))
				result = cur.fetchone()
				return result if result else None
		except Exception as e:
				logging.error(f"Error getting vendor response for user {user_id} and email_id {email_id}: {str(e)}")
				raise

	def update_vendor_response(
		self,
		user_id: str,
		email_id: str,
		vendor_emails: Optional[List[str]] = None,
		request_body: Optional[str] = None,
		generated_body: Optional[str] = None,
		subject: Optional[str] = None,
		email_analysis: Optional[Dict] = None,
		radius: Optional[int] = None,
		plane_size: Optional[str] = None,
		number_of_passengers: Optional[int] = None
	) -> Optional[str]:
		"""
		Update a vendor response for a given userId and emailId, only updating fields that are not None (using COALESCE logic).
		Returns the id of the updated row, or None if not found.
		"""
		try:
			with self.get_cursor(commit=True) as cur:
				cur.execute('''
					UPDATE "VendorResponse"
					SET
						"vendorEmails" = COALESCE(%s, "vendorEmails"),
						"requestBody" = COALESCE(%s, "requestBody"),
						"responseBody" = COALESCE(%s, "responseBody"),
						"responseSubject" = COALESCE(%s, "responseSubject"),
						"updatedAt" = %s,
						"emailAnalysis" = COALESCE(%s, "emailAnalysis"),
						"radius" = COALESCE(%s, "radius"),
						"planeSize" = COALESCE(%s, "planeSize"),
						"numPassengers" = COALESCE(%s, "numPassengers")
					WHERE "userId" = %s AND "emailId" = %s
					RETURNING id;
				''', (
					vendor_emails,
					request_body,
					generated_body,
					subject,
					datetime.now(),
					Jsonb(email_analysis) if email_analysis is not None else None,
					radius,
					plane_size,
					number_of_passengers,
					user_id,
					email_id
				))
				result = cur.fetchone()
				return result['id'] if result else None
		except Exception as e:
				logging.error(f"Error updating vendor response for user {user_id} and email_id {email_id}: {str(e)}")
				raise