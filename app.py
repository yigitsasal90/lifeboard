from flask import Flask, render_template, request, redirect
import sqlite3
import os

app = Flask(__name__)

DB_NAME = "lifeboard.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS routine_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            energy TEXT,
            soreness TEXT,
            activity TEXT,
            notes TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS boo_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            appetite TEXT,
            energy TEXT,
            toilet TEXT,
            scratching TEXT,
            notes TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS finance_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            usd REAL,
            eur REAL,
            gold REAL,
            interest REAL,
            comment TEXT
        )
    """)

    conn.commit()
    conn.close()


@app.route("/")
def home():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT id, date, energy, soreness, activity, notes
        FROM routine_logs
        ORDER BY id DESC
        LIMIT 10
    """)
    routine_logs = c.fetchall()
    latest_routine = routine_logs[0] if routine_logs else None

    c.execute("""
        SELECT id, date, appetite, energy, toilet, scratching, notes
        FROM boo_logs
        ORDER BY id DESC
        LIMIT 10
    """)
    boo_logs = c.fetchall()
    latest_boo = boo_logs[0] if boo_logs else None

    c.execute("""
        SELECT id, date, usd, eur, gold, interest, comment
        FROM finance_snapshots
        ORDER BY id DESC
        LIMIT 10
    """)
    finance_logs = c.fetchall()
    latest_finance = finance_logs[0] if finance_logs else None

    conn.close()

    return render_template(
        "dashboard.html",
        routine_logs=routine_logs,
        latest_routine=latest_routine,
        boo_logs=boo_logs,
        latest_boo=latest_boo,
        finance_logs=finance_logs,
        latest_finance=latest_finance
    )


@app.route("/add-routine", methods=["POST"])
def add_routine():
    date = request.form.get("date")
    energy = request.form.get("energy")
    soreness = request.form.get("soreness")
    activity = request.form.get("activity")
    notes = request.form.get("notes")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        INSERT INTO routine_logs (date, energy, soreness, activity, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (date, energy, soreness, activity, notes))

    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/add-boo", methods=["POST"])
def add_boo():
    date = request.form.get("boo_date")
    appetite = request.form.get("boo_appetite")
    energy = request.form.get("boo_energy")
    toilet = request.form.get("boo_toilet")
    scratching = request.form.get("boo_scratching")
    notes = request.form.get("boo_notes")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        INSERT INTO boo_logs (date, appetite, energy, toilet, scratching, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (date, appetite, energy, toilet, scratching, notes))

    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/add-finance", methods=["POST"])
def add_finance():
    date = request.form.get("finance_date")
    usd = request.form.get("finance_usd")
    eur = request.form.get("finance_eur")
    gold = request.form.get("finance_gold")
    interest = request.form.get("finance_interest")
    comment = request.form.get("finance_comment")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        INSERT INTO finance_snapshots (date, usd, eur, gold, interest, comment)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (date, usd, eur, gold, interest, comment))

    conn.commit()
    conn.close()

    return redirect("/")


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
