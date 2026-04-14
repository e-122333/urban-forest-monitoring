import streamlit as st
import ee
import json
import sqlite3
import pandas as pd
import geemap.foliumap as geemap
from streamlit_folium import st_folium
from datetime import datetime, timedelta

# --- 1. AUTHENTICATION ---
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
    st.error("No Earth Engine credentials found in Secrets.")
    st.stop()

# --- 2. CONSTANTS (SRS 4.1 & SDD 8) ---
NDVI_VIS_PARAMS = {
    'min': -0.2,
    'max': 0.2,
    'palette': ['#A50026', '#F46D43', '#FFFFBF', '#74C476', '#006837']
}

# Regional Bounding Boxes for Dynamic Metrics
REGION_COORDS = {
    "Northern Region": ee.Geometry.Rectangle([73.0, 28.0, 80.0, 36.0]),
    "Western Region": ee.Geometry.Rectangle([68.0, 18.0, 77.0, 30.0]),
    "Eastern Region": ee.Geometry.Rectangle([83.0, 19.0, 97.0, 29.0]),
    "Southern Region": ee.Geometry.Rectangle([74.0, 8.0, 80.0, 20.0]),
    "Central Region": ee.Geometry.Rectangle([77.0, 21.0, 84.0, 30.0])
}
INDIA_BOUNDS = ee.Geometry.Rectangle([68.1, 6.5, 97.4, 35.5])

# --- 3. UI SETUP & SIDEBAR (Must come before Logic) ---
st.set_page_config(layout="wide", page_title="EcoScan - India")

with st.sidebar:
    st.title("👤 EcoScan Profile")
    # Regional Chunk Selection (This defines selected_chunk)
    selected_chunk = st.selectbox("Select Regional Chunk (SRS 4.1)", list(REGION_COORDS.keys()))
    
    st.divider()
    if st.button("Logout"): st.stop()

# --- 4. DYNAMIC COMPUTATION LOGIC ---
def get_ndvi_with_stats(roi, start_date, end_date):
    """Calculates NDVI image and the Mean NDVI value for metrics."""
    s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
        .filterBounds(roi) \
        .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
        .median()
    
    ndvi_image = s2.normalizedDifference(['B8', 'B4'])
    
    # Calculate Mean for the Metric Box (SDD 3.1.1)
    # Using scale=500 for fast calculation on a large regional area
    stats = ndvi_image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=roi,
        scale=500,
        maxPixels=1e9
    )
    return ndvi_image, stats

# --- 5. DASHBOARD DISPLAY ---
st.title("🌳 EcoScan: India Greenery Monitoring")

# Date Selectors
d_col1, d_col2 = st.columns(2)
start_dt = d_col1.date_input("Start Date", datetime(2024, 1, 1))
end_dt = d_col2.date_input("End Date", datetime.now())

# Perform the dynamic calculation based on sidebar selection
target_roi = REGION_COORDS[selected_chunk]

try:
    with st.spinner(f"Computing health index for {selected_chunk}..."):
        ndvi_layer, stats_output = get_ndvi_with_stats(target_roi, start_dt, end_dt)
        mean_val = stats_output.get('nd').getInfo()
        
        # Display Dynamic Metrics
        m1, m2, m3 = st.columns(3)
        m1.metric(f"{selected_chunk} Health", f"{mean_val:.3f} NDVI", delta="Live Calculation")
        m2.metric("Critical Alerts", "5", "High Severity")
        m3.metric("System Status", "Live", delta_color="normal")

    # --- 6. MAP VIEW ---
    st.subheader(f"🗺️ Interactive NDVI Map: {selected_chunk}")
    m = geemap.Map(center=[20.5, 78.9], zoom=5, ee_initialize=False)
    
    # Add NDVI Layer
    m.addLayer(ndvi_layer, NDVI_VIS_PARAMS, f'NDVI {selected_chunk}')
    
    # Center map on the selected region
    m.centerObject(target_roi, 6)
    
    st_folium(m, width=1200, height=550)

except Exception as e:
    st.error(f"Error during computation: {e}")
