import threading
from dotenv import load_dotenv
import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
import logging
# For compatibility
from contracts import VendorResponses
from postgres_client import PostgresClient
from rabbitmq_client import RabbitMQClient
# Provider-specific consumer (FlightListPro)
from workflows.flightlistpro.consumer import FlightListProConsumer
from contextlib import asynccontextmanager


load_dotenv()

# Configure logging
logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)

logger = logging.getLogger(__name__)

# Initialize clients
rabbitmq_client = RabbitMQClient()
db = PostgresClient()

# Initialize provider consumer(s)
consumer = FlightListProConsumer(
       rabbitmq_client=rabbitmq_client,
       postgres_client=db,
)


def run_rabbitmq():
	"""Run the RabbitMQ consumer"""
	try:
		logger.info("Starting RabbitMQ consumer...")
		# Start consuming emails via provider consumer
		consumer.consume_emails()
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

@app.get("/health")
async def health_check():
	"""
	Health check endpoint for Fly.io to monitor application health.
	This endpoint should return a 200 OK response if the application is healthy.
	"""
	try:
		# Check database connection
		with db.get_connection() as conn:
			conn.execute("SELECT 1")
		
		# Check RabbitMQ connection
		rabbitmq_client.ensure_connection()
		
		return {"status": "healthy", "database": "connected", "rabbitmq": "connected"}
	except Exception as e:
		logger.error(f"Health check failed: {str(e)}")
		raise HTTPException(status_code=503, detail=f"Service unavailable: {str(e)}")

# TODO: recompute-flight-plan will be reimplemented in upcoming refactor.

@app.get("/vendor-responses/{user_id}", response_model=VendorResponses)
async def get_vendor_responses(
	user_id: str,
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

@app.get("/results/{user_id}")
async def get_results(
	user_id: str,
	result_type: Optional[str] = None,
	page: int = 1,
	page_size: int = 10,
):
	try:
		return db.get_processing_results_for_user(
			user_id=user_id,
			result_type=result_type,
			page=page,
			page_size=page_size,
		)
	except Exception as e:
		logger.error(f"Error getting results: {str(e)}")
		raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
	uvicorn.run(app, host="0.0.0.0", port=8000) 