import logging
from typing import Any, Dict, List

from langchain_core.tools import tool

# Provider-scoped email processor
from workflows.flightlistpro.email_processor import EmailProcessor
from tools.flight_finder import FlightFinderClient

# ---------- internal helper factories ----------

def _email_processor() -> EmailProcessor:
    return EmailProcessor()


def _flight_finder() -> FlightFinderClient:
    return FlightFinderClient()

# ---------- provider-specific tools ------------

@tool(name_or_callable="flightlistpro_parse_email", description="Parse an incoming email body and extract charter request details for FlightListPro workflow.")
def flightlistpro_parse_email(email_body: str) -> Dict[str, Any]:
    """Return analysis JSON (see EmailProcessor.analyze_incoming_email)."""
    logging.info(f"flightlistpro_parse_email:Parsing email: {email_body}")
    ep = _email_processor()
    return ep.analyze_incoming_email(email_body)


@tool(name_or_callable="flightlistpro_search_vendors", description="Search FlightListPro database for vendor emails that satisfy the extracted flight parameters.")
def flightlistpro_search_vendors(analysis: Dict[str, Any]) -> List[str]:
    """Given the analysis JSON from flightlistpro_parse_email, return a list of vendor email addresses."""
    logging.info(f"flightlistpro_search_vendors: Searching for vendors in tool call: {analysis}")
    ff = _flight_finder()
    flight = analysis["flights"][0]
    origin = flight.get("origin")
    pax = flight.get("passengers")
    size = flight.get("aircraft_size")
    radius = 0  # default radius for now

    # If size is None or not recognised, search without size filter
    sizes = [size] if size else []
    vendor_emails = ff.search(origin, pax, sizes, radius)
    print(f"[FlightFinder] origin={origin} pax={pax} size={size} -> {len(vendor_emails)} vendors")
    return vendor_emails


@tool(name_or_callable="flightlistpro_compose_email", description="Compose a customer-facing itinerary email based on the extracted analysis for FlightListPro.")
def flightlistpro_compose_email(analysis: Dict[str, Any]) -> Dict[str, str]:
    logging.info(f"flightlistpro_compose_email: Composing email in tool call: {analysis}")
    ep = _email_processor()
    return ep.build_email(analysis) 