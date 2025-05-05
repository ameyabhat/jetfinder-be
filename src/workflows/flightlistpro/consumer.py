import pprint
import logging
import traceback
from typing import Dict, Any, Union

from rabbitmq_client import RabbitMQClient
from postgres_client import PostgresClient
from workflows.flightlistpro.email_processor import EmailProcessor

# Supervisor graph (provider-agnostic)
from supervisor_graph import supervisor_graph

class FlightListProConsumer:
    """Provider-specific email consumer that interfaces with RabbitMQ and DB."""

    FlightPlanError = "FlightPlanError"
    NoVendorEmailsFound = "NoVendorEmailsFound"
    UnknownError = "UnknownError"

    def __init__(
        self,
        rabbitmq_client: RabbitMQClient,
        postgres_client: PostgresClient,
    ):
        self.rabbitmq_client = rabbitmq_client
        self.postgres_client = postgres_client

    # ------------------------------------------------------------------
    # Rabbit entry-point
    # ------------------------------------------------------------------

    def process_email_external(self, message):
        try:
            self._process_email(message)
        except Exception as e:
            logging.error(f"Error processing email: {e}")
            self.rabbitmq_client.send_error_message(
                queues=[
                    self.rabbitmq_client.InternalErrorQueue,
                    self.rabbitmq_client.ManualInterventionQueue,
                ],
                message=message,
                error_type=self.UnknownError,
                **{"error": str(e), "stacktrace": traceback.format_exc()},
            )

    # ------------------------------------------------------------------
    # Core logic (delegates to supervisor graph)
    # ------------------------------------------------------------------

    def _process_email(self, message: Dict[str, Any]):
        email_content = message.get("content", "")
        if not email_content:
            logging.info("Empty email body – skipping")
            return

        initial_state = {"messages": [{"role": "user", "content": email_content}]}
        logging.info(f"Initial state: {initial_state}")
        logging.info("Running supervisor graph for FlightListPro email …")
        try:
            result_state = supervisor_graph.invoke(initial_state)
        except Exception as e:
            logging.error(f"Supervisor graph error: {e}")
            raise

        # LangGraph stores langchain messages; they may be ChatMessage objects
        final_messages = result_state.get("messages", []) if result_state else []
        if not final_messages:
            logging.error(f"No final supervisor message – aborting, {result_state}")
            return

        final_msg = final_messages[-1]

        # Extract content whether it's a dict or a BaseMessage instance
        if isinstance(final_msg, dict):
            raw_content = final_msg.get("content", "{}")
        else:
            # langchain BaseMessage / AIMessage
            raw_content = getattr(final_msg, "content", "{}")

        import json

        try:
            payload = json.loads(raw_content)
        except json.JSONDecodeError:
            logging.info(f"Payload: {raw_content}")
            logging.error("Supervisor final content is not valid JSON – aborting")
            return

        if payload.get("skip"):
            logging.info("Supervisor says: not a charter request – skipping")
            return
        logging.info(f"Payload: {payload}")
        vendor_emails = payload.get("vendor_emails", [])
        if not vendor_emails:
            logging.info("Supervisor found no vendors – flagging intervention")
            self.rabbitmq_client.send_error_message(
                queues=[self.rabbitmq_client.ManualInterventionQueue],
                message=message,
                error_type=self.NoVendorEmailsFound,
            )
            return

        analysis = payload.get("email_analysis", {})
        generated_email = payload.get("generated_email", {})

        payload = {
            "vendor_emails": vendor_emails,
            "generated_email": generated_email,
            "email_analysis": analysis,
        }

        self.postgres_client.write_processing_result(
            user_email=message.get("user_email"),
            email_id=message.get("email_id"),
            provider="flightlistpro",
            result_type="vendor_response",
            payload=payload,
        )

    # ------------------------------------------------------------------
    # Public method for RabbitMQ consumer thread
    # ------------------------------------------------------------------

    def consume_emails(self):
        self.rabbitmq_client.consume_messages(
            queue_name=self.rabbitmq_client.EmailQueue,
            callback=self.process_email_external,
        ) 