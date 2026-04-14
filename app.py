import streamlit as st
import ee
import json
import sqlite3
import pandas as pd
import geemap.foliumap as geemap
from streamlit_folium import st_folium
from datetime import datetime, timedelta

# --- 1. AUTHENTICATION (EcoScan SDD 3.1.1) ---
if 'GEE_JSON_KEY' in st.secrets:
    try:
        raw_json = st.secrets['GEE_JSON_KEY']
        info = json.loads(raw_json)
        # Service Account Credentials with raw JSON to prevent bytes/auth errors
        credentials = ee.ServiceAccountCredentials(info['client_email'], key_data=raw_json)
        ee.Initialize(credentials=credentials)
    except Exception as e:
        st.error(f"EcoScan GEE Auth Failed: {e}")
        st.stop()
else:
    st.error("No Earth Engine credentials found. Please check Streamlit Secrets.")
    st.stop()

# --- 2. DATABASE INITIALIZATION (EcoScan SDD 4.2) ---
def init_db():
    conn = sqlite3.connect('urban_forest.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, username TEXT, threshold REAL, email_alerts INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS alerts 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, district TEXT, loss_area REAL, severity TEXT)''')
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users (id, username, threshold, email_alerts) VALUES (1, 'AdminUser', 0.2, 1)")
    conn.commit()
    conn.close()

init_db()

# --- 3. CONSTANTS & REGIONS (From SRS 4.1 & SDD 8) ---
NDVI_VIS_PARAMS = {
    'min': -0.2,
    'max': 0.2,
    'palette': ['#A50026', '#F46D43', '#FFFFBF', '#74C476', '#006837']
}

# Regional Bounding Boxes (SRS 4.1)
REGION_COORDS = {
    "Northern Region": ee.Geometry.Rectangle([73.0, 28.0, 80.0, 36.0]),
    "Western Region": ee.Geometry.Rectangle([68.0, 18.0, 77.0, 30.0]),
    "Eastern Region": ee.Geometry.Rectangle([83.0, 19.0, 97.0, 29.0]),
    "Southern Region": ee.Geometry.Rectangle([74.0, 8.0, 80.0, 20.0]),
    "Central Region": ee.Geometry.Rectangle([77.0, 21.0, 84.0, 30.0])
}

# --- 4. OPTIMIZED GEE COMPUTATION ---
def get_ndvi_with_stats(roi, start_date, end_date):
    """
    Computes NDVI and handles memory-efficient statistical reduction.
    Optimization: scale=1000 and bestEffort=True prevents Memory Limit Exceeded.
    """
    s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
        .filterBounds(roi) \
        .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
        .median()
    
    ndvi_image = s2.normalizedDifference(['B8', 'B4'])
    
    # Statistical reduction for the Metric Card
    stats = ndvi_image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=roi,
        scale=1000,   # Aggregates to 1km to save user memory
        maxPixels=1e8,
        bestEffort=True
    )
    return ndvi_image, stats

# --- 5. STREAMLIT UI ---
st.set_page_config(layout="wide", page_title="EcoScan - India Greenery Monitor")

# Sidebar
with st.sidebar:
    st.title("👤 EcoScan Profile")
    selected_chunk = st.selectbox("Select Regional Chunk (SRS 4.1)", list(REGION_COORDS.keys()))
    st.divider()
    if st.button("Logout"): st.stop()

# Main Dashboard
st.title("🌳 EcoScan: India Greenery Monitoring System")

# Date Inputs
d_col1, d_col2 = st.columns(2)
start_dt = d_col1.date_input("Start Date", datetime(2024, 1, 1))
end_dt = d_col2.date_input("End Date", datetime.now())

# Analysis logic
target_roi = REGION_COORDS[selected_chunk]

try:
    with st.spinner(f"Processing satellite data for {selected_chunk}..."):
        # Real-time GEE Computation
        ndvi_layer, stats_output = get_ndvi_with_stats(target_roi, start_dt, end_dt)
        mean_ndvi = stats_output.get('nd').getInfo()
        
        # If no images found, mean_ndvi will be None
        if mean_ndvi is None: mean_ndvi = 0.0

        # UI Metrics (Dynamic based on region)
        m1, m2, m3 = st.columns(3)
        m1.metric(f"{selected_chunk} Health", f"{mean_ndvi:.3f} NDVI", delta="Real-time Avg")
        m2.metric("Critical Alerts", "5", "High Severity")
        m3.metric("System Status", "Live", delta_color="normal")

    # --- 6. MAP VIEW ---
    st.subheader(f"🗺️ {selected_chunk} Vegetation Index Map")
    m = geemap.Map(center=[20.5, 78.9], zoom=5, ee_initialize=False)
    
    # Add NDVI Layer with the SDD 5-category palette
    m.addLayer(ndvi_layer, NDVI_VIS_PARAMS, f'NDVI - {selected_chunk}')
    m.centerObject(target_roi, 6)
    
    st_folium(m, width=1200, height=550)

except Exception as e:
    st.error(f"Error during EcoScan computation: {e}")

# --- 7. RECENT ALERTS (SRS 4.3) ---
st.divider()
st.subheader("📋 Recent Environmental Alerts")

conn = sqlite3.connect('urban_forest.db')
alerts_df = pd.read_sql_query("SELECT * FROM alerts ORDER BY id DESC", conn)
conn.close()

if not alerts_df.empty:
    st.dataframe(alerts_df, use_container_width=True)
else:
    st.info("No significant vegetation loss detected for this region in the selected timeframe.")

if st.button("🚀 Run Manual Detection Sync"):
    # Simulated detection event
    conn = sqlite3.connect('urban_forest.db')
    c = conn.cursor()
    c.execute("INSERT INTO alerts (date, district, loss_area, severity) VALUES (?, ?, ?, ?)",
              (datetime.now().strftime("%Y-%m-%d"), "Regional Sample", 0.72, "High"))
    conn.commit()
    conn.close()
    st.rerun()
