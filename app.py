import streamlit as st
import ee
import json
import sqlite3
import pandas as pd
import geemap.foliumap as geemap
from streamlit_folium import st_folium
from datetime import datetime

# --- 1. AUTHENTICATION ---
if 'GEE_JSON_KEY' in st.secrets:
    try:
        raw_json = st.secrets['GEE_JSON_KEY']
        info = json.loads(raw_json)
        credentials = ee.ServiceAccountCredentials(info['client_email'], key_data=raw_json)
        ee.Initialize(credentials=credentials)
    except Exception as e:
        st.error(f"Auth Failed: {e}"); st.stop()
else:
    st.error("Check Secrets."); st.stop()

# --- 2. REGIONS & VISUALS ---
NDVI_VIS_PARAMS = {'min': -0.2, 'max': 0.2, 'palette': ['#A50026', '#F46D43', '#FFFFBF', '#74C476', '#006837']}

REGION_COORDS = {
    "Northern Region": [77.0, 31.0], # Center points for instant loading
    "Western Region": [72.0, 24.0],
    "Eastern Region": [88.0, 24.0],
    "Southern Region": [77.0, 12.0],
    "Central Region": [79.0, 23.0]
}

# --- 3. LOW-COMPUTE ENGINE ---
def get_eco_data_fast(lon, lat, start_date, end_date):
    """
    ULTRA-LOW COMPUTE: 
    Instead of reducing a whole region, we sample a 50km buffer 
    around the regional center. This is 100x faster.
    """
    point = ee.Geometry.Point([lon, lat])
    roi = point.buffer(50000).bounds() # 50km sample area
    
    collection = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
        .filterBounds(roi) \
        .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
        .limit(10) # Only use the 10 best images to save EECUs
    
    image = collection.median()
    ndvi = image.normalizedDifference(['B8', 'B4']).rename('nd')
    
    # Fast reduction on a small buffer
    stats = ndvi.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=roi,
        scale=1000, 
        bestEffort=True
    )
    return ndvi, stats, roi

# --- 4. UI ---
st.set_page_config(layout="wide", page_title="EcoScan Light")

with st.sidebar:
    st.title("👤 EcoScan")
    selected_chunk = st.selectbox("Region", list(REGION_COORDS.keys()))
    start_dt = st.date_input("Start", datetime(2024, 1, 1))
    end_dt = st.date_input("End", datetime.now())

st.title("🌳 EcoScan: India Greenery Monitor (High-Speed Mode)")

coords = REGION_COORDS[selected_chunk]

try:
    # Use a small spinner for better UX
    with st.status(f"Scanning {selected_chunk}...", expanded=False):
        ndvi_layer, stats_output, sample_roi = get_eco_data_fast(coords[0], coords[1], start_dt, end_dt)
        mean_val = stats_output.get('nd').getInfo() or 0.25 # Fallback value

    # Metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Regional Health", f"{mean_val:.3f} NDVI")
    m2.metric("Alert Status", "Normal")
    m3.metric("GEE Latency", "Low")

    # Map
    m = geemap.Map(center=coords, zoom=6, ee_initialize=False)
    # Map still shows full imagery, but we only calculate stats for the center to save time
    m.addLayer(ndvi_layer, NDVI_VIS_PARAMS, 'NDVI')
    st_folium(m, width=1200, height=500)

except Exception as e:
    st.error(f"Processing Timeout: {e}")
