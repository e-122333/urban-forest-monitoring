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
        credentials = ee.ServiceAccountCredentials(info['client_email'], key_data=raw_json)
        ee.Initialize(credentials=credentials)
    except Exception as e:
        st.error(f"EcoScan GEE Auth Failed: {e}")
        st.stop()
else:
    st.error("Missing GEE_JSON_KEY in Streamlit Secrets.")
    st.stop()

# --- 2. DATABASE INIT ---
def init_db():
    conn = sqlite3.connect('urban_forest.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, threshold REAL, email_alerts INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, district TEXT, loss_area REAL, severity TEXT)')
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users (id, username, threshold, email_alerts) VALUES (1, 'AdminUser', 0.2, 1)")
    conn.commit()
    conn.close()

init_db()

# --- 3. REGIONS & VISUALS (SRS 4.1 / SDD 8) ---
NDVI_VIS_PARAMS = {
    'min': -0.2,
    'max': 0.2,
    'palette': ['#A50026', '#F46D43', '#FFFFBF', '#74C476', '#006837']
}

# Simplified Bounding Boxes to reduce geometry complexity
REGION_COORDS = {
    "Northern Region": ee.Geometry.BBox(73.0, 28.0, 80.0, 36.0),
    "Western Region": ee.Geometry.BBox(68.0, 18.0, 77.0, 30.0),
    "Eastern Region": ee.Geometry.BBox(83.0, 19.0, 97.0, 29.0),
    "Southern Region": ee.Geometry.BBox(74.0, 8.0, 80.0, 20.0),
    "Central Region": ee.Geometry.BBox(77.0, 21.0, 84.0, 30.0)
}

# --- 4. ULTIMATE OPTIMIZED COMPUTATION ---
def get_ndvi_optimized(roi, start_date, end_date):
    """
    Uses heavy downsampling (scale=2000) and tile-based reduction
    to prevent 'Memory Limit Exceeded' on large Indian regions.
    """
    # Load Sentinel-2 Collection
    collection = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
        .filterBounds(roi) \
        .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
    
    # Create Median Composite (SDD 3.1.1)
    median_image = collection.median()
    
    # Calculate NDVI
    ndvi = median_image.normalizedDifference(['B8', 'B4']).rename('nd')
    
    # PERFORMANCE FIX: Reduce the region using a very large scale (2km per pixel)
    # This turns millions of pixels into a few hundred, preventing memory errors.
    stats = ndvi.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=roi,
        scale=2000, 
        maxPixels=1e7,
        bestEffort=True
    )
    
    return ndvi, stats

# --- 5. STREAMLIT UI ---
st.set_page_config(layout="wide", page_title="EcoScan - India Monitor")

with st.sidebar:
    st.title("👤 EcoScan Profile")
    selected_chunk = st.selectbox("Select Regional Chunk", list(REGION_COORDS.keys()))
    if st.button("Logout"): st.stop()

st.title("🌳 EcoScan: India Greenery Monitoring System")

d_col1, d_col2 = st.columns(2)
start_dt = d_col1.date_input("Start Date", datetime(2024, 1, 1))
end_dt = d_col2.date_input("End Date", datetime.now())

target_roi = REGION_COORDS[selected_chunk]

try:
    with st.spinner(f"Analyzing {selected_chunk} (this may take 10-20 seconds)..."):
        # Fetch data
        ndvi_layer, stats_output = get_ndvi_optimized(target_roi, start_dt, end_dt)
        
        # Safe extraction of the mean value
        stats_dict = stats_output.getInfo()
        mean_val = stats_dict.get('nd', 0.0) if stats_dict else 0.0

        # UI Metrics
        m1, m2, m3 = st.columns(3)
        m1.metric(f"{selected_chunk} Health", f"{mean_val:.3f} NDVI", delta="Avg Health")
        m2.metric("Critical Alerts", "5", "High Severity")
        m3.metric("System Status", "Live", delta_color="normal")

    # --- 6. MAP VIEW ---
    st.subheader(f"🗺️ {selected_chunk} Vegetation Index")
    m = geemap.Map(center=[20.5, 78.9], zoom=5, ee_initialize=False)
    m.addLayer(ndvi_layer, NDVI_VIS_PARAMS, 'EcoScan NDVI')
    m.centerObject(target_roi, 6)
    
    st_folium(m, width=1200, height=550)

except Exception as e:
    st.error(f"Computation failed for {selected_chunk}. Error: {e}")
    st.info("Try selecting a smaller date range if this persists.")

# --- 7. ALERTS LOG ---
st.divider()
st.subheader("📋 Recent Environmental Alerts")
conn = sqlite3.connect('urban_forest.db')
alerts_df = pd.read_sql_query("SELECT * FROM alerts ORDER BY id DESC", conn)
conn.close()
st.dataframe(alerts_df, use_container_width=True)
