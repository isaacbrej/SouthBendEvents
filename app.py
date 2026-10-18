import json
from datetime import date, datetime, timedelta
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="South Bend Event Dashboard", page_icon="🎟️", layout="wide"
)


def format_event_datetime(iso_str):
    """Converts ISO timestamp strings into user-friendly readable dates and times."""
    if not iso_str or pd.isna(iso_str) or iso_str == "TBD":
        return "Date & Time TBD"

    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        # Format: Friday, Oct 24, 2026 @ 7:00 PM
        formatted_date = dt.strftime("%A, %b %d, %Y")
        formatted_time = dt.strftime("%I:%M %p").lstrip("0")
        return f"{formatted_date} @ {formatted_time}"
    except Exception:
        return str(iso_str)


@st.cache_data
def load_events():
    with open("normalized_events.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)

    dt_series = pd.to_datetime(df["iso_start_time"], utc=True, errors="coerce")
    df["datetime"] = dt_series
    df["date"] = dt_series.dt.date

    # Format human-readable date strings
    df["display_datetime"] = df["iso_start_time"].apply(format_event_datetime)

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

CATEGORY_EMOJIS = {
    "Civic & Community Affairs": "🏛️",
    "Live Music": "🎵",
    "Nightlife & Pubs": "🍺",
    "Shows & Arts": "🎭",
    "Sports & Recreation": "⚽",
    "Festivals & Community": "🎪",
    "Community & Social": "👥",
}

# -------------------------------------------------------------------
# 1. 7-DAY UPCOMING CALENDAR AT THE TOP (Excludes Civic Meetings)
# -------------------------------------------------------------------
st.subheader("📅 Next 7 Days At A Glance (Social & Fun)")

today = date.today()
next_7_days = [today + timedelta(days=i) for i in range(7)]

# Filter top calendar to social/leisure events only by default
social_df = df[df["category"] != "Civic & Community Affairs"]

cols = st.columns(7)

for idx, day in enumerate(next_7_days):
    with cols[idx]:
        day_str = day.strftime("%a, %b %d")
        if day == today:
            st.markdown(f"**📌 TODAY**\n`{day_str}`")
        else:
            st.markdown(f"**{day.strftime('%A')}**\n`{day_str}`")

        day_events = social_df[social_df["date"] == day]

        if day_events.empty:
            st.caption("No social events")
        else:
            st.markdown(f"**{len(day_events)} Event(s)**")
            for _, ev in day_events.iterrows():
                cat = ev.get("category", "General")
                emoji = CATEGORY_EMOJIS.get(cat, "📌")
                title = ev.get("title", "Untitled")
                venue = ev.get("venue", "N/A")
                dt_fmt = ev.get("display_datetime", "TBD")

                with st.expander(f"{emoji} {title[:25]}..."):
                    st.write(f"**Venue:** {venue}")
                    st.write(f"**When:** `{dt_fmt}`")
                    st.write(f"**Category:** {cat}")
                    if pd.notna(ev.get("link")):
                        st.markdown(f"[🔗 View Event Link]({ev['link']})")

st.divider()

# -------------------------------------------------------------------
# 2. SIDEBAR FILTERS
# -------------------------------------------------------------------
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

# -------------------------------------------------------------------
# 3. DETAILED EVENT BREAKDOWN BY CATEGORY & VENUE
# -------------------------------------------------------------------
st.subheader("📊 Event Breakdown & Metrics")

m1, m2, m3 = st.columns(3)
m1.metric("Total Active Listings", len(filtered_df))
m2.metric("Active Venues", filtered_df["venue"].nunique())
m3.metric("Active Categories", filtered_df["category"].nunique())

col_cat, col_ven = st.columns(2)

with col_cat:
    with st.expander("📂 Events Count per Category", expanded=True):
        cat_counts = (
            filtered_df["category"]
            .value_counts()
            .reset_index()
            .rename(columns={"index": "Category", "count": "Events Count"})
        )
        st.dataframe(cat_counts, use_container_width=True, hide_index=True)

with col_ven:
    with st.expander("📍 Events Count per Venue", expanded=True):
        venue_counts = (
            filtered_df["venue"]
            .value_counts()
            .reset_index()
            .rename(columns={"index": "Venue", "count": "Events Count"})
        )
        st.dataframe(venue_counts, use_container_width=True, hide_index=True)

st.divider()

# Refresh Scraper Button
if st.button("🔄 Refresh Scraper & Reload Data"):
    st.cache_data.clear()
    st.success("Data reloaded successfully!")
    st.rerun()

# -------------------------------------------------------------------
# 4. PRIMARY EVENT DISPLAY TABS
# -------------------------------------------------------------------
tab_community, tab_civic, tab_calendar = st.tabs(
    [
        "🎉 Social & Leisure Events",
        "🏛️ Civic & Professional Affairs",
        "📅 Interactive Calendar View",
    ]
)


def render_event_list(events_df):
    if events_df.empty:
        st.info("No events found matching your filter criteria.")
        return

    for _, row in events_df.iterrows():
        with st.container():
            c1, c2 = st.columns([3, 1])
            cat_name = row.get("category", "General")
            emoji = CATEGORY_EMOJIS.get(cat_name, "📌")
            display_dt = row.get("display_datetime", "TBD")

            with c1:
                st.subheader(row.get("title", "Untitled Event"))
                st.write(
                    f"📍 **Venue:** {row.get('venue', 'N/A')} ({row.get('city', 'South Bend')})"
                )
                st.write(
                    f"🕒 **When:** `{display_dt}` | **Category:** `{emoji} {cat_name}`"
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
    # Strictly non-civic/professional leisure events
    community_df = filtered_df[
        filtered_df["category"] != "Civic & Community Affairs"
    ]
    render_event_list(community_df)

with tab_civic:
    # Civic, municipal, board, council, workshop, & training meetings
    civic_df = filtered_df[
        filtered_df["category"] == "Civic & Community Affairs"
    ]
    render_event_list(civic_df)

with tab_calendar:
    st.subheader("Event Timetable")

    show_civic = st.checkbox(
        "Include Civic & Professional Events in Calendar View", value=False
    )

    cal_filtered = (
        filtered_df
        if show_civic
        else filtered_df[filtered_df["category"] != "Civic & Community Affairs"]
    )

    if not cal_filtered.empty:
        cal_df = cal_filtered[
            ["date", "display_datetime", "title", "venue", "category"]
        ].sort_values("date")
        cal_df = cal_df.rename(columns={"display_datetime": "Formatted Date & Time"})
        st.dataframe(cal_df, use_container_width=True)
    else:
        st.info("No events available for calendar view.")