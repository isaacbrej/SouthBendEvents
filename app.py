import json
from datetime import date, datetime
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="South Bend Event Dashboard", page_icon="🎟️", layout="wide"
)


@st.cache_data
def load_events():
    with open("normalized_events.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)

    dt_series = pd.to_datetime(df["iso_start_time"], utc=True, errors="coerce")
    df["datetime"] = dt_series
    df["date"] = dt_series.dt.date

    return df


try:
    df = load_events()
except Exception as e:
    st.error(f"Error loading events data: {e}")
    st.stop()

# Header & Control Bar
st.title("🏙️ South Bend & Mishawaka Event Aggregator")
st.markdown(
    "Discover live music, nightlife, civic affairs, performing arts, sports, and community events across the region."
)

# Sidebar Filters
st.sidebar.header("Filter Events")

# Category Filter
all_categories = sorted(df["category"].dropna().unique().tolist())
selected_categories = st.sidebar.multiselect(
    "Category", options=all_categories, default=all_categories
)

# Venue Filter
all_venues = sorted(df["venue"].dropna().unique().tolist())
selected_venues = st.sidebar.multiselect("Venue", options=all_venues)

# Clean valid dates for date picker
valid_dates = [d for d in df["date"].dropna().tolist() if isinstance(d, date)]
min_date = min(valid_dates) if valid_dates else date.today()
max_date = max(valid_dates) if valid_dates else date.today()

date_range = st.sidebar.date_input("Date Range", value=(min_date, max_date))

# Filter Logic
filtered_df = df.copy()

if selected_categories:
    filtered_df = filtered_df[
        filtered_df["category"].isin(selected_categories)
    ]

if selected_venues:
    filtered_df = filtered_df[filtered_df["venue"].isin(selected_venues)]

if isinstance(date_range, tuple) and len(date_range) == 2:
    start_d, end_d = date_range
    date_mask = (filtered_df["date"] >= start_d) & (
        filtered_df["date"] <= end_d
    )
    filtered_df = filtered_df[date_mask | filtered_df["date"].isna()]

# KPI Summary Cards
col1, col2, col3 = st.columns(3)
col1.metric("Total Listings", len(filtered_df))
col2.metric("Active Venues", filtered_df["venue"].nunique())
col3.metric("Categories", filtered_df["category"].nunique())

st.divider()

# Refresh Scraper Button
if st.button("🔄 Refresh Scraper & Reload Data"):
    st.cache_data.clear()
    st.success("Data reloaded successfully!")
    st.rerun()

# Tabs: Community Events, Civic & Government Meetings, and Interactive Calendar
tab_community, tab_civic, tab_calendar = st.tabs(
    [
        "🎉 Community & Social Events",
        "🏛️ Civic & Community Government",
        "📅 Interactive Calendar View",
    ]
)

CATEGORY_EMOJIS = {
    "Civic & Community Affairs": "🏛️",
    "Live Music": "🎵",
    "Nightlife & Pubs": "🍺",
    "Shows & Arts": "🎭",
    "Sports & Recreation": "⚽",
    "Festivals & Community": "🎪",
    "Community & Social": "👥",
}


def render_event_list(events_df):
    if events_df.empty:
        st.info("No events found matching your filter criteria.")
        return

    for _, row in events_df.iterrows():
        with st.container():
            c1, c2 = st.columns([3, 1])
            cat_name = row.get("category", "General")
            emoji = CATEGORY_EMOJIS.get(cat_name, "📌")

            with c1:
                st.subheader(row.get("title", "Untitled Event"))
                st.write(
                    f"**Venue:** {row.get('venue', 'N/A')} ({row.get('city', 'South Bend')})"
                )
                st.write(
                    f"**Category:** `{emoji} {cat_name}` | **Date/Time:** {row.get('iso_start_time', 'TBD')}"
                )
                if pd.notna(row.get("link")):
                    st.markdown(f"[🔗 View Original Event Link]({row['link']})")
            with c2:
                if pd.notna(row.get("ics_export")):
                    st.download_button(
                        label="📅 Download .ics",
                        data=row["ics_export"],
                        file_name=f"{row.get('id', 'event')}.ics",
                        mime="text/calendar",
                        key=f"btn_{row.get('id')}",
                    )
            st.divider()


with tab_community:
    community_df = filtered_df[
        filtered_df["category"] != "Civic & Community Affairs"
    ]
    render_event_list(community_df)

with tab_civic:
    civic_df = filtered_df[
        filtered_df["category"] == "Civic & Community Affairs"
    ]
    render_event_list(civic_df)

with tab_calendar:
    st.subheader("Event Timetable")

    show_civic = st.checkbox(
        "Include Civic & Government Meetings in Calendar View", value=False
    )

    cal_filtered = (
        filtered_df
        if show_civic
        else filtered_df[filtered_df["category"] != "Civic & Community Affairs"]
    )

    if not cal_filtered.empty:
        cal_df = cal_filtered[["date", "title", "venue", "category"]].sort_values(
            "date"
        )
        st.dataframe(cal_df, use_container_width=True)
    else:
        st.info("No events available for calendar view.")