import threading
from dotenv import load_dotenv
import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
from postgres_client import PostgresClient
from rabbitmq_client import RabbitMQClient
from email_processor import EmailProcessor
from search_orchestrator import FlightUpdateRequest, SearchOrchestrator
from tools.flight_finder import FlightFinderClient
from contextlib import asynccontextmanager


load_dotenv()

# Configure logging
logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)

logger = logging.getLogger(__name__)

# Initialize clients
rabbitmq_client = RabbitMQClient()
email_processor = EmailProcessor()
flight_finder = FlightFinderClient()
db = PostgresClient()

# Initialize orchestrator
orchestrator = SearchOrchestrator(
	   rabbitmq_client=rabbitmq_client,
	   email_processor=email_processor,
  	   flight_finder=flight_finder,
  	   postgres_client=db
)



class VendorResponseList(BaseModel):
	responses: List[dict]
	total: int
	page: int
	total_pages: int

def run_rabbitmq():
	"""Run the RabbitMQ consumer"""
	try:
		logger.info("Starting RabbitMQ consumer...")
		# Start consuming emails
		orchestrator.consume_emails()
	except Exception as e:
		logger.error(f"RabbitMQ consumer error: {str(e)}")
		raise

def start_rabbitmq_consumer():
	"""Start the RabbitMQ consumer in a separate thread"""
	rabbitmq_thread = threading.Thread(target=run_rabbitmq)
	rabbitmq_thread.daemon = True  # This ensures the thread will exit when the main program exits
	rabbitmq_thread.start()
	logger.info("RabbitMQ consumer thread started")

# Start the RabbitMQ consumer when the application starts
@asynccontextmanager
async def lifespan(app: FastAPI):
	start_rabbitmq_consumer()
	yield

app = FastAPI(
	title="JetFinder API",
	description="API for managing flight search and vendor responses",
	version="1.0.0",
	lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],  # In production, replace with specific origins
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

#  API endpoints
@app.get("/")
async def root():
	return {"message": "Welcome to JetFinder API"}

@app.post("/recompute-flight-plan/", response_model=dict)
async def recompute_flight_plan(request: FlightUpdateRequest):
	try:
		response = orchestrator.update_flight_search(request)

		if response == orchestrator.UnknownError:
			raise HTTPException(status_code=500, detail="Unknown error")
		elif response == orchestrator.NoVendorEmailsFound:
			raise HTTPException(status_code=400, detail="No vendor emails found")
		else:
			return response
	except Exception as e:
		logger.error(f"Error creating vendor response: {str(e)}")
		raise HTTPException(status_code=500, detail=str(e))

@app.get("/vendor-responses/{user_id}", response_model=VendorResponseList)
async def get_vendor_responses(
	user_id: int,
	page: int = 1,
	page_size: int = 10,
	sort_order: str = 'desc'
):
	try:
		return db.get_vendor_responses_for_user(
			user_id=user_id,
			page=page,
			page_size=page_size,
			sort_order=sort_order
		)
	except Exception as e:
		logger.error(f"Error getting vendor responses: {str(e)}")
		raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
	uvicorn.run(app, host="0.0.0.0", port=8000) 