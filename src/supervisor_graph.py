from typing import Annotated, Dict, Any

# LangGraph / LangChain imports
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent, InjectedState
from langgraph.graph import StateGraph, START, MessagesState
from langgraph.types import Command
from langchain_core.tools import tool, InjectedToolCallId

# FlightListPro provider-specific tools
from workflows.flightlistpro.tools import (
    flightlistpro_parse_email,
    flightlistpro_search_vendors,
    flightlistpro_compose_email,
)

"""
Supervisor graph for JetFinder
==============================
This module builds and exposes a LangGraph "supervisor" graph with two agents:
    1. supervisor_agent – decides which workflow agent to hand off to (for now always
       FlightListPro but the design supports multiple in the future).
    2. flightlistpro_agent – performs the FlightListPro email-processing workflow
       using three internal tools (parse_email, search_vendors, compose_email).

The graph can be imported and invoked from business logic, e.g.
    from supervisor_graph import supervisor_graph
    result = supervisor_graph.invoke({"messages": [initial_message]})

The final supervisor message contains the JSON payload expected by SearchOrchestrator.
"""

###########################################################################
# Helper tool imports for FlightListPro workflow                          #
###########################################################################

###########################################################################
# FlightListPro agent definition                                          #
###########################################################################

flightlistpro_agent = create_react_agent(
    model=init_chat_model("openai:gpt-4o-mini"),
    tools=[flightlistpro_parse_email, flightlistpro_search_vendors, flightlistpro_compose_email],
    prompt=(
        "You are the FlightListPro workflow agent for JetFinder.\n\n"
        "INSTRUCTIONS:\n"
        "1. Your input will be a raw email body (string).\n"
        "2. First, call `flightlistpro_parse_email` to extract analysis JSON.\n"
        "3. If `is_charter_request` is false, immediately respond to the supervisor with JSON {\"skip\": true}.\n"
        "4. Otherwise, call `flightlistpro_search_vendors` with the analysis to get a list of vendor email addresses.\n"
        "5. After calling `flightlistpro_search_vendors`, check the result. **IF AND ONLY IF** the returned list of vendor emails is NOT empty, proceed to step 6. \n"
        "6. **IF THE LIST IS EMPTY**, STOP IMMEDIATELY. Respond ONLY with JSON: {\"provider\": \"flightlistpro\", \"result_type\": \"vendor_response\", \"vendor_emails\": []}. DO NOT CALL ANY OTHER TOOLS.\n"
        "7. **IF THE LIST IS NOT EMPTY**, call `flightlistpro_compose_email` to obtain subject/body.\n"
        "8. When all tasks are complete, respond ONLY with valid JSON in the form (include `generated_email` only if step 7 was performed):\n"
        "   {\n"
        "     \"provider\": \"flightlistpro\",\n"
        "     \"result_type\": \"vendor_response\",\n"
        "     \"vendor_emails\": [...],\n"
        "     \"email_analysis\": <analysis>,\n"
        "     \"generated_email\": {\"subject\": ..., \"body\": ...}\n"
        "   }\n"
        "Do not include any extra commentary."
    ),
    name="flightlistpro_agent",
)

###########################################################################
# Supervisor agent setup                                                 #
###########################################################################


def _create_handoff_tool(agent_name: str, description: str | None = None):
    """Factory for hand-off tools used by the supervisor."""
    name = f"transfer_to_{agent_name}"
    description = description or f"Transfer work to {agent_name}."

    @tool(name, description=description)
    def _handoff_tool(
        state: Annotated[MessagesState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        tool_msg = {
            "role": "tool",
            "content": f"Successfully transferred to {agent_name}",
            "name": name,
            "tool_call_id": tool_call_id,
        }
        new_state = {"messages": state["messages"] + [tool_msg]}
        return Command(goto=agent_name, update=new_state, graph=Command.PARENT)

    return _handoff_tool


# Only one workflow agent today
assign_to_flightlistpro = _create_handoff_tool(
    agent_name="flightlistpro_agent",
    description="Assign the current e-mail to the FlightListPro workflow agent.",
)

supervisor_agent = create_react_agent(
    model=init_chat_model("openai:gpt-4o-mini"),
    tools=[assign_to_flightlistpro],
    prompt=(
        "You are the supervisor agent for JetFinder.\n"
        "For every incoming message, decide which workflow agent should handle it.\n"
        "Currently, ONLY the FlightListPro workflow is supported, so route everything to it.\n"
        "After a workflow agent returns, output its JSON result to the caller with no edits.\n"
        "Do not perform any other work yourself."
    ),
    name="supervisor",
)

###########################################################################
# Graph compilation                                                      #
###########################################################################

_supervisor_graph_internal = (
    StateGraph(MessagesState)
    .add_node(supervisor_agent, destinations=("flightlistpro_agent",))
    .add_node(flightlistpro_agent)
    .add_edge(START, "supervisor")
    .add_edge("flightlistpro_agent", "supervisor")
    .compile()
)

# Public handle – other modules import this
supervisor_graph = _supervisor_graph_internal 