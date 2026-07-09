import streamlit as st
import pandas as pd
import plotly.express as px
from serpapi import GoogleSearch
import anthropic
import os
import json

SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY")

# Expanded hub list
HUBS = [
    "JFK", "EWR", "ORD", "LAX", "IAD", "ATL", "BOS",
    "DEN", "DFW", "SLC", "SEA", "MSP", "SFO",
    "PHX", "MCO", "IAH", "MDW", "LGA", "DTW", "MIA"
]

def extract_trip_details(user_query):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    prompt = f"""Extract trip details from this request and return ONLY a JSON object, no other text:

"{user_query}"

Return exactly this format:
{{
  "origin1_code": "IATA airport code for first traveler's origin (e.g. BZN)",
  "origin1_name": "City name for first origin",
  "origin2_code": "IATA airport code for second traveler's origin (e.g. LIT)",
  "origin2_name": "City name for second origin",
  "destination_code": "IATA airport code for destination city (e.g. IST)",
  "destination_name": "Full destination city name (e.g. Istanbul)",
  "traveler1_name": "Name or label for first traveler (e.g. S)",
  "traveler2_names": "Names or label for second travelers (e.g. A & G)"
}}

Important:
- Use the closest major airport to each city mentioned
- Return ONLY the JSON, no explanation"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    response_text = message.content[0].text.strip()
    response_text = response_text.replace("```json", "").replace("```", "").strip()
    return json.loads(response_text)

def search_direct_flights(origin, destination, date):
    params = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": date,
        "currency": "USD",
        "hl": "en",
        "api_key": SERPAPI_KEY,
        "type": "2"
    }
    search = GoogleSearch(params)
    results = search.get_dict()
    flights = results.get("best_flights", []) + results.get("other_flights", [])
    direct = []
    for flight in flights:
        legs = flight.get("flights", [])
        layovers = flight.get("layovers", [])
        if len(layovers) == 0 and len(legs) == 1:
            direct.append({
                "origin": origin,
                "destination": destination,
                "airline": legs[0].get("airline", "Unknown"),
                "price": flight.get("price", 9999),
                "duration": flight.get("total_duration", 0)
            })
    return direct

def get_claude_recommendation(itineraries, user_query, trip, optimize_for):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    summary = ""
    for i in itineraries:
        summary += f"""
Hub: {i['hub']}
  - {trip['traveler1_name']} flies {trip['origin1_code']} -> {i['hub']} on {i['o1_airline']} for USD {i['o1_price']}
  - {trip['traveler2_names']} fly {trip['origin2_code']} -> {i['hub']} on {i['o2_airline']} for USD {i['o2_price']} each (USD {i['o2_price']*2} total)
  - All fly {i['hub']} -> {trip['destination_code']} on {i['dest_airline']} for USD {i['dest_price']} each (USD {i['dest_price']*3} total)
  - Group total: USD {i['total']}
  - Solo traveler ({trip['traveler1_name']}) cost: USD {i['o1_price']}
  - Total travel time: {i['total_duration']} minutes
"""

    optimization_note = {
        "Cheapest total for the group": "prioritize the lowest total group cost",
        "Cheapest for the solo traveler (Traveler 1)": f"prioritize the lowest cost specifically for {trip['traveler1_name']}, the solo traveler flying alone",
        "Shortest total travel time": "prioritize the fastest total travel time across all travelers",
        "Best balance of price and time": "find the best balance between cost and travel time"
    }[optimize_for]

    prompt = f"""You are a helpful travel advisor. A user asked:

{user_query}

They want to {optimization_note}.

Based on real flight data retrieved today, here are all viable itinerary options where everyone flies direct to a hub and then direct together to {trip['destination_name']}:

{summary}

Please recommend the best option based on their optimization preference. Include:
1. Which hub city to meet at and why
2. Each person's specific flight and cost
3. Total group cost and {trip['traveler1_name']}'s individual cost
4. Total travel time
5. One practical travel tip for {trip['destination_name']}
Keep it friendly, clear and concise."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

# ── STREAMLIT APP ──────────────────────────────────────
st.set_page_config(page_title="AI Group Flight Optimizer", page_icon="✈️")
st.title("✈️ AI-Powered Group Flight Optimizer")
st.markdown("Find the best way for your group to meet at a US hub and fly together to any international destination — using real flight data and Claude AI.")

with st.expander("📌 How this app works & current limitations", expanded=True):
    st.markdown("""
**What this app does:**
Finds the best US hub city where two parties flying from different US cities can meet on direct flights, then fly together direct to an international destination.

**To get the best results, your prompt should clearly mention:**
- The name or label of each traveler (e.g. "Sarah", "A & E", "my parents")
- The specific US city each traveler flies from
- The international destination city you all want to reach
- Note: When optimizing for **"Cheapest for the solo traveler"**, the app minimizes cost for the **first traveler mentioned** in your prompt (e.g. "Sam & Sammy" in the example below)

**Current limitations:**
- Works for any **2 US origin cities**
- Checks **20 major US hub airports**: JFK, EWR, ORD, LAX, IAD, ATL, BOS, DEN, DFW, SLC, SEA, MSP, SFO, PHX, MCO, IAH, MDW, LGA, DTW, MIA
- Requires **direct flights only** at every leg — no connections
- Not all hub-to-destination routes have direct flights; results depend on what airlines actually fly
- Prices are real-time but may change by booking time

**Example prompt:**
> *Sam & Sammy live in La Crosse, WI and Anne & Annie live in San Antonio, TX. They all want to fly together to Paris. What is the cheapest way for the group to meet at a US hub and then fly to Paris together?*
""")

st.divider()

user_query = st.text_area(
    "Describe your trip:",
    placeholder="Describe your group's trip — mention each traveler's name, their US city, and where you all want to fly together internationally.",
)

col1, col2 = st.columns(2)
with col1:
    travel_date = st.date_input("Day everyone flies to the hub city:")
with col2:
    dest_date = st.date_input("Day everyone flies to destination:")

optimize_for = st.selectbox(
    "Optimize for:",
    [
        "Cheapest total for the group",
        "Cheapest for the solo traveler (Traveler 1)",
        "Shortest total travel time",
        "Best balance of price and time"
    ]
)

search_button = st.button("Find Best Itinerary ✈️", type="primary")

if search_button and user_query:

    with st.spinner("Reading your trip details with Claude..."):
        try:
            trip = extract_trip_details(user_query)
            st.info(f"✅ Got it! Searching: **{trip['origin1_name']}** ({trip['origin1_code']}) + **{trip['origin2_name']}** ({trip['origin2_code']}) → hub → **{trip['destination_name']}** ({trip['destination_code']})")
        except Exception as e:
            st.error("Could not extract trip details. Please make sure your prompt mentions two US origin cities and an international destination clearly.")
            st.stop()

    travel_date_str = travel_date.strftime("%Y-%m-%d")
    dest_date_str = dest_date.strftime("%Y-%m-%d")

    with st.spinner(f"Searching direct flights from {trip['origin1_code']} to all hubs..."):
        o1_flights = []
        for hub in HUBS:
            o1_flights.extend(search_direct_flights(trip['origin1_code'], hub, travel_date_str))

    with st.spinner(f"Searching direct flights from {trip['origin2_code']} to all hubs..."):
        o2_flights = []
        for hub in HUBS:
            o2_flights.extend(search_direct_flights(trip['origin2_code'], hub, travel_date_str))

    o1_hubs = set(f["destination"] for f in o1_flights)
    o2_hubs = set(f["destination"] for f in o2_flights)
    common_hubs = o1_hubs & o2_hubs

    if not common_hubs:
        st.error(f"No common hub airports found with direct flights from both {trip['origin1_code']} and {trip['origin2_code']}. Try different dates or origin cities.")
        st.stop()

    with st.spinner(f"Searching direct flights from hubs to {trip['destination_name']}..."):
        dest_flights = []
        for hub in common_hubs:
            dest_flights.extend(search_direct_flights(hub, trip['destination_code'], dest_date_str))

    itineraries = []
    for hub in common_hubs:
        o1_options = [f for f in o1_flights if f["destination"] == hub]
        o2_options = [f for f in o2_flights if f["destination"] == hub]
        dest_options = [f for f in dest_flights if f["origin"] == hub]

        if not o1_options or not o2_options or not dest_options:
            continue

        cheapest_o1 = min(o1_options, key=lambda x: x["price"])
        cheapest_o2 = min(o2_options, key=lambda x: x["price"])
        cheapest_dest = min(dest_options, key=lambda x: x["price"])

        total = (cheapest_o1["price"] +
                 cheapest_o2["price"] * 2 +
                 cheapest_dest["price"] * 3)
        total_duration = (cheapest_o1["duration"] +
                         cheapest_o2["duration"] +
                         cheapest_dest["duration"])

        itineraries.append({
            "hub": hub,
            "o1_airline": cheapest_o1["airline"],
            "o1_price": cheapest_o1["price"],
            "o2_airline": cheapest_o2["airline"],
            "o2_price": cheapest_o2["price"],
            "dest_airline": cheapest_dest["airline"],
            "dest_price": cheapest_dest["price"],
            "total": total,
            "total_duration": total_duration
        })

    sort_key = {
        "Cheapest total for the group": "total",
        "Cheapest for the solo traveler (Traveler 1)": "o1_price",
        "Shortest total travel time": "total_duration",
        "Best balance of price and time": "total"
    }[optimize_for]

    itineraries.sort(key=lambda x: x[sort_key])

    if not itineraries:
        st.warning(f"No complete itineraries found with direct flights to {trip['destination_name']}. Try different dates or a nearby major airport.")
        st.stop()

    # Display results
    y_axis = {
        "Cheapest total for the group": "total",
        "Cheapest for the solo traveler (Traveler 1)": "o1_price",
        "Shortest total travel time": "total_duration",
        "Best balance of price and time": "total"
    }[optimize_for]

    y_label = {
        "total": "Total Group Cost (USD)",
        "o1_price": f"{trip['traveler1_name']}'s Cost (USD)",
        "total_duration": "Total Travel Time (minutes)"
    }[y_axis]

    st.subheader(f"💰 Results by Hub City (sorted by: {optimize_for})")
    df = pd.DataFrame(itineraries)

    fig = px.bar(
        df, x="hub", y=y_axis,
        labels={"hub": "Hub City", y_axis: y_label},
        color=y_axis,
        color_continuous_scale="blues",
        text=y_axis
    )
    fig.update_traces(texttemplate='%{text:,}', textposition='outside')
    fig.update_layout(showlegend=False, coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("📋 All Options")
    display_df = df[["hub", "o1_price", "o2_price", "dest_price", "total", "total_duration"]].copy()
    display_df.columns = [
        "Hub",
        f"{trip['traveler1_name']}: {trip['origin1_code']}→Hub",
        f"{trip['traveler2_names']}: {trip['origin2_code']}→Hub (each)",
        f"Hub→{trip['destination_code']} (each)",
        "Group Total",
        "Total Duration (min)"
    ]
    st.dataframe(display_df, use_container_width=True)

    st.subheader("🤖 Claude's Recommendation")
    with st.spinner("Asking Claude for the best recommendation..."):
        recommendation = get_claude_recommendation(itineraries, user_query, trip, optimize_for)
    st.markdown(recommendation)

elif search_button and not user_query:
    st.warning("Please describe your trip first.")

st.divider()
st.caption("Built with Python, SerpApi, Claude AI, Streamlit & GitHub")
