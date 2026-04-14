import streamlit as st
import ee
import json
import sqlite3
import pandas as pd
import geemap.foliumap as geemap
from datetime import datetime, timedelta

# --- 1. AUTHENTICATION & INITIALIZATION ---
if 'GEE_JSON_KEY' in st.secrets:
    try:
        raw_json = st.secrets['GEE_JSON_KEY']
        info = json.loads(raw_json)
        credentials = ee.ServiceAccountCredentials(info['client_email'], key_data=raw_json)
        ee.Initialize(credentials=credentials)
    except Exception as e:
        st.error(f"Google Earth Engine Auth Failed: {e}")
        st.stop()
else:
    try:
        ee.Initialize()
    except:
        ee.Authenticate()
        ee.Initialize()

# --- 2. DATABASE UTILITIES ---
def init_db():
    """Initializes the SQLite database for the cloud environment."""
    conn = sqlite3.connect('urban_forest.db')
    c = conn.cursor()
    # Create Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, username TEXT, threshold REAL, email_alerts INTEGER)''')
    # Create Alerts table
    c.execute('''CREATE TABLE IF NOT EXISTS alerts 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, district TEXT, loss_area REAL, severity TEXT)''')
    
    # Insert a default user if the table is empty
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users (id, username, threshold, email_alerts) VALUES (1, 'AdminUser', 0.2, 1)")
    
    conn.commit()
    conn.close()

# Run database setup
init_db()

def get_user_settings():
    conn = sqlite3.connect('urban_forest.db')
    df = pd.read_sql_query("SELECT * FROM users WHERE id=1", conn)
    conn.close()
    return df.iloc[0]

def log_alert(district, loss_area):
    conn = sqlite3.connect('urban_forest.db')
    c = conn.cursor()
    severity = "High" if loss_area > 0.5 else "Medium"
    c.execute("INSERT INTO alerts (date, district, loss_area, severity) VALUES (?, ?, ?, ?)",
              (datetime.now().strftime("%Y-%m-%d"), district, loss_area, severity))
    conn.commit()
    conn.close()

# --- 3. STREAMLIT UI SETUP ---
st.set_page_config(layout="wide", page_title="Urban Forest Intelligence")

# Sidebar: Profile & Navigation
with st.sidebar:
    st.title("👤 User Profile")
    settings = get_user_settings()
    st.write(f"Logged in: **{settings['username']}**")
    
    with st.expander("⚙️ Settings"):
        new_thresh = st.slider("Detection Threshold", 0.1, 0.5, float(settings['threshold']))
        email_opt = st.checkbox("Enable Notifications", value=bool(settings['email_alerts']))
        if st.button("Save Preferences"):
            # Update Logic
            conn = sqlite3.connect('urban_forest.db')
            c = conn.cursor()
            c.execute("UPDATE users SET threshold=?, email_alerts=? WHERE id=1", (new_thresh, int(email_opt)))
            conn.commit()
            conn.close()
            st.success("Preferences Saved!")
    
    if st.button("Logout"): 
        st.stop()

# --- 4. DASHBOARD CONTENT ---
st.title("🌳 Urban Forest Monitoring System")

# Summary Metrics (Dummy data for demo)
col1, col2, col3 = st.columns(3)
col1.metric("Current Health Index", "0.62 NDVI", "+2%")
col2.metric("Alerts This Week", "12", "-3")
col3.metric("System Status", "Live", delta_color="normal")

# --- 5. SATELLITE ENGINE (GEE) ---
def get_ndvi_layer(roi, start_date, end_date):
    s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
        .filterBounds(roi) \
        .filterDate(start_date, end_date) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10)) \
        .median()
    return s2.normalizedDifference(['B8', 'B4'])

# Map View Setup
st.subheader("🗺️ Interactive Monitoring Map")

# Date Selectors
d_col1, d_col2 = st.columns(2)
start = d_col1.date_input("Start Date", datetime.now() - timedelta(days=365))
end = d_col2.date_input("End Date", datetime.now())

# Initialize Map
m = geemap.Map(center=[40.78, -73.96], zoom=13, ee_initialize=False) 
roi = ee.Geometry.Point([-73.96, 40.78]).buffer(2000)

# Generate and Add NDVI
try:
    ndvi = get_ndvi_layer(roi, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
    m.addLayer(ndvi, {'min': 0, 'max': 1, 'palette': ['red', 'yellow', 'green']}, 'Current NDVI')
    m.centerObject(roi, 14)
except Exception as e:
    st.warning(f"Could not load satellite data: {e}")

m.to_streamlit(height=500)

# --- 6. DISTRICT CARDS & REPORTS ---
st.divider()
st.subheader("📋 District Status & Alerts")

# Manual Trigger for Demo Purposes
if st.button("🚀 Run Manual Sync (Detect New Loss)"):
    log_alert("North District", 0.8)
    st.rerun()

# Display Alerts from SQL
conn = sqlite3.connect('urban_forest.db')
alerts_df = pd.read_sql_query("SELECT * FROM alerts ORDER BY id DESC", conn)
conn.close()

if not alerts_df.empty:
    st.dataframe(alerts_df, use_container_width=True)
    st.download_button("📥 Download Report", alerts_df.to_csv(index=False), "forest_report.csv")
else:
    st.info("No illegal removals detected in the selected timeframe.")
