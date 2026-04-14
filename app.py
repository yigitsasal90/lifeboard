from flask import Flask
import sqlite3

app = Flask(__name__)

DB_NAME = "lifeboard.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS routine_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            energy TEXT,
            soreness TEXT,
            activity TEXT,
            notes TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS boo_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            appetite TEXT,
            energy TEXT,
            toilet TEXT,
            scratching TEXT,
            notes TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS finance_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            usd REAL,
            eur REAL,
            gold REAL,
            interest REAL,
            comment TEXT
        )
    ''')

    conn.commit()
    conn.close()

@app.route("/")
def home():
    return "LifeBoard hazır 🚀"

if __name__ == "__main__":
    init_db()
    app.run()
