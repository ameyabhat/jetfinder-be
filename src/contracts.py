from pydantic import BaseModel
from typing import List, Optional

class VendorResponses(BaseModel):
	responses: List[dict]
	total: int
	page: int
	total_pages: int


# Pydantic models for request/response validation
class FlightUpdateRequest(BaseModel):
	user_id: str
	message_id: str
	plane_size: Optional[str] = None
	search_radius: Optional[int] = None
	number_of_passengers: Optional[int] = None

