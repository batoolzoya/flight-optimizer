import streamlit as st
import pandas as pd
import plotly.express as px
from serpapi import GoogleSearch
import anthropic

# ── CONFIG ──────────────────────────────────────────────
import os
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY")

HUBS = ["JFK", "EWR", "ORD", "LAX", "IAD", 
        "ATL", "BOS", "DEN", "DFW", "SLC", "SEA", "MSP", "SFO"]

# ── FLIGHT SEARCH ────────────────────────────────────────
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

# ── CLAUDE RECOMMENDATION ────────────────────────────────
def get_claude_recommendation(itineraries, user_query):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    summary = ""
    for i in itineraries:
summary += f"""
Hub: {i['hub']}
  - S flies BZN -> {i['hub']} on {i['bzn_airline']} for USD {i['bzn_price']}
  - A & G fly LIT -> {i['hub']} on {i['lit_airline']} for USD {i['lit_price']} each (USD {i['lit_price']*2} total)
  - All three fly {i['hub']} -> IST on {i['ist_airline']} for USD {i['ist_price']} each (USD {i['ist_price']*3} total)
  - Group total: USD {i['total']}
"""
    prompt = f"""You are a helpful travel advisor. A user asked:

{user_query}

Based on real flight data retrieved today, here are all viable itinerary options:

{summary}

Please recommend the best option clearly and warmly. Include:
1. Which hub city to meet at and why
2. Each person's specific flight and cost
3. Total cost for the group
4. One practical travel tip
Keep it friendly, clear and concise."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

# ── STREAMLIT APP ────────────────────────────────────────
st.set_page_config(page_title="AI Flight Optimizer", page_icon="✈️")
st.title("✈️ AI-Powered Group Flight Optimizer")
st.markdown("Find the cheapest way for your group to meet and fly together — using real flight data and Claude AI.")

st.divider()

# User input
user_query = st.text_area(
    "Describe your trip:",
    placeholder='e.g. S and his parents A&G want to fly to Istanbul together. S lives in Bozeman, MT and A&G live in North Little Rock, AR. They want direct flights only, meeting at a hub city on the same day, then flying to Istanbul together the next day.',
    height=120
)

travel_date = st.date_input("Day everyone flies to the hub city:")
istanbul_date = st.date_input("Day everyone flies to Istanbul:")

search_button = st.button("Find Best Itinerary ✈️", type="primary")

if search_button and user_query:
    with st.spinner("Searching real-time flights..."):
        travel_date_str = travel_date.strftime("%Y-%m-%d")
        istanbul_date_str = istanbul_date.strftime("%Y-%m-%d")

        # Search BZN → hubs
        bzn_flights = []
        for hub in HUBS:
            bzn_flights.extend(search_direct_flights("BZN", hub, travel_date_str))

        # Search LIT → hubs
        lit_flights = []
        for hub in HUBS:
            lit_flights.extend(search_direct_flights("LIT", hub, travel_date_str))

        # Find common hubs
        bzn_hubs = set(f["destination"] for f in bzn_flights)
        lit_hubs = set(f["destination"] for f in lit_flights)
        common_hubs = bzn_hubs & lit_hubs

        # Search common hubs → IST
        ist_flights = []
        for hub in common_hubs:
            ist_flights.extend(search_direct_flights(hub, "IST", istanbul_date_str))

        # Build itineraries
        itineraries = []
        for hub in common_hubs:
            bzn_options = [f for f in bzn_flights if f["destination"] == hub]
            lit_options = [f for f in lit_flights if f["destination"] == hub]
            ist_options = [f for f in ist_flights if f["origin"] == hub]

            if not bzn_options or not lit_options or not ist_options:
                continue

            cheapest_bzn = min(bzn_options, key=lambda x: x["price"])
            cheapest_lit = min(lit_options, key=lambda x: x["price"])
            cheapest_ist = min(ist_options, key=lambda x: x["price"])

            total = (cheapest_bzn["price"] +
                     cheapest_lit["price"] * 2 +
                     cheapest_ist["price"] * 3)

            itineraries.append({
                "hub": hub,
                "bzn_airline": cheapest_bzn["airline"],
                "bzn_price": cheapest_bzn["price"],
                "lit_airline": cheapest_lit["airline"],
                "lit_price": cheapest_lit["price"],
                "ist_airline": cheapest_ist["airline"],
                "ist_price": cheapest_ist["price"],
                "total": total
            })

        itineraries.sort(key=lambda x: x["total"])

    if itineraries:
        # Bar chart
        st.subheader("💰 Total Group Cost by Hub City")
        df = pd.DataFrame(itineraries)
        fig = px.bar(
            df, x="hub", y="total",
            labels={"hub": "Hub City", "total": "Total Group Cost (USD)"},
            color="total",
            color_continuous_scale="blues",
            text="total"
        )
        fig.update_traces(texttemplate='$%{text:,}', textposition='outside')
        fig.update_layout(showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

        # Itinerary table
        st.subheader("📋 All Options")
        display_df = df[["hub", "bzn_price", "lit_price", "ist_price", "total"]].copy()
        display_df.columns = ["Hub", "S: BZN→Hub", "A&G: LIT→Hub (each)", "Hub→IST (each)", "Group Total"]
        display_df = display_df.sort_values("Group Total")
        st.dataframe(display_df, use_container_width=True)

        # Claude recommendation
        st.subheader("🤖 Claude's Recommendation")
        with st.spinner("Asking Claude for the best recommendation..."):
            recommendation = get_claude_recommendation(itineraries, user_query)
        st.markdown(recommendation)

    else:
        st.error("No complete itineraries found. Try different dates.")

elif search_button and not user_query:
    st.warning("Please describe your trip first.")

st.divider()
st.caption("Built with Python, SerpApi, Claude AI, and Streamlit")
