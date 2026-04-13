import sqlite3

def init_db():
    conn = sqlite3.connect('urban_forest.db')
    c = conn.cursor()
    
    # User Profile & Settings
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, username TEXT, email_alerts INTEGER, threshold REAL)''')
    
    # Alert History
    c.execute('''CREATE TABLE IF NOT EXISTS alerts 
                 (id INTEGER PRIMARY KEY, date TEXT, district TEXT, loss_area REAL, severity TEXT)''')
    
    # Insert a dummy user if not exists
    c.execute("INSERT OR IGNORE INTO users (id, username, email_alerts, threshold) VALUES (1, 'Admin', 1, 0.25)")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()