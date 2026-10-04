import os
import certifi
from dotenv import load_dotenv

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from typing import TypedDict, Annotated
import operator
import uuid
import asyncio

import psycopg
from psycopg.rows import dict_row

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    SystemMessage
)
from langchain_groq import ChatGroq
#from tools.tavily_tool import tavily_search
from tools.flight_tool import search_flights
from mcp_client_test import tavily_mcp_search

def get_database_url():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "DATABASE_URL is missing. Please add your Render PostgreSQL External Database URL to .env"
        )

    if "sslmode" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"
    
    return database_url

import json

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing. Please add it to your .env file")

llm = ChatGroq(
    model = "openai/gpt-oss-20b",
    api_key = GROQ_API_KEY,
    temperature = 0
)

def format_mcp_hotel_results(raw_mcp_output, max_items=5, snippet_len=250):
    try:
        combined_text = ""
        if isinstance(raw_mcp_output, list):
            for block in raw_mcp_output:
                if isinstance(block, dict) and block.get("type") == "text":
                    combined_text += block.get("text", "") + "\n"
        elif isinstance(raw_mcp_output, str):
            combined_text = raw_mcp_output

        data = json.loads(combined_text)
        results = data.get("results", [])

        formatted = []
        for idx, item in enumerate(results[:max_items], 1):
            title = item.get("title", "Hotel Option")
            url = item.get("url", "")
            snippet = item.get("content", "")[:snippet_len].replace("\n", " ")
            formatted.append(f"{idx}. {title}\n   URL: {url}\n   Info: {snippet}")

        return "\n\n".join(formatted) if formatted else combined_text[:1500]
    except Exception:
        return str(raw_mcp_output)[:1500]

class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str
    flight_results: str
    hotel_results: str
    itinerary: str
    llm_calls: int

# ====================================
# Flight Agent
# ====================================

def flight_agent(state: TravelState):
    query = state["user_query"]
    flight_data = search_flights(query)

    return {
        "flight_results": flight_data,
        "messages": [
            AIMessage(content='Flight results fetched.')
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }

# ====================================
# Hotel Agent
# ====================================

def hotel_agent(state: TravelState):
    query = f"Best hotels for {state['user_query']}"
    raw_hotel_results = asyncio.run(tavily_mcp_search(query))
    formatted_hotels = format_mcp_hotel_results(raw_hotel_results)

    return {
        "hotel_results": formatted_hotels,
        "messages": [
            AIMessage(content="Hotel results fetched")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }




# ==================================
# Itinerary Agent
# ==================================

def itinerary_agent(state:TravelState):
    prompt = f"""
Create a complete travel itinerary.

User Query:
{state['user_query']}

Flight Results:
{state['flight_results']}

Hotel Results:
{state['hotel_results']}

Make the itinerary practical, budget-aware, and easy to follow.
"""

    response = llm.invoke([
        SystemMessage(content="You are an expert travel planner."),
        HumanMessage(content=prompt)
    ])

    return {
        "itinerary": response.content,
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }

# =======================================
# Final Response Agent
# =======================================

def final_agent(state: TravelState):
    final_prompt = f"""
Generate the final travel response for the user.

User Request:
{state['user_query']}

Flights:
{state['flight_results']}

Hotels:
{state['hotel_results']}

Itinerary:
{state['itinerary']}

Format the final answer beautifully using these sections:

1. Trip Summary
2. Flight Information
3. Hotel Suggestions
4. Day-by-Day Itinerary
5. Estimated Budget
6. Final Recommendations

Important:
- Be clear and practical.
- Mention that live flight API may not provide ticket prices if pricing is unavailable.
- Keep the response useful for real travel planning.
"""

    response = llm.invoke([
        SystemMessage(content="You are a professional AI travel booking assistant."),
        HumanMessage(content=final_prompt)
    ])

    return {
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }

# =======================================
# Build Graph
# =======================================

graph = StateGraph(TravelState)
graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("final_agent", final_agent)

graph.add_edge(START, "flight_agent")
graph.add_edge("flight_agent", "hotel_agent")
graph.add_edge("hotel_agent", "itinerary_agent")
graph.add_edge("itinerary_agent", "final_agent")
graph.add_edge("final_agent", END)

# ===============================================
# PostgreSQL Checkpointer
# ===============================================
DATABASE_URL = get_database_url()

_conn = psycopg.connect(
    DATABASE_URL,
    autocommit=True,
    row_factory=dict_row
)

checkpointer = PostgresSaver(_conn)
checkpointer.setup()

travel_graph = graph.compile(checkpointer=checkpointer)

#=================================================
# Function for FastAPI
# ================================================

def run_travel_agent(user_input: str, thread_id: str | None = None):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    result = travel_graph.invoke(
        {
            "messages": [
                HumanMessage(content=user_input)
            ],
            "user_query": user_input,
            "flight_results": "",
            "hotel_results": "",
            "itinerary": "",
            "llm_calls": 0
        },
        config=config
    )

    final_answer = result["messages"][-1].content

    return {
        "thread_id": thread_id,
        "answer": final_answer,
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "itinerary": result.get("itinerary", ""),
        "llm_calls": result.get("llm_calls", 0),
    }