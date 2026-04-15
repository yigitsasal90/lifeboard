from flask import Flask, render_template, request, redirect
import sqlite3
import os
import json
from datetime import datetime, date
import requests

app = Flask(__name__)

DB_PATH = "lifeboard.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS routine_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_date TEXT NOT NULL,
            mood TEXT NOT NULL,
            energy TEXT NOT NULL,
            pain TEXT NOT NULL,
            activity TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS winnie_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_date TEXT NOT NULL,
            appetite TEXT NOT NULL,
            energy TEXT NOT NULL,
            toilet TEXT NOT NULL,
            itch TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS vaccine_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vaccine_date TEXT NOT NULL,
            vaccine_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def today_str():
    return date.today().isoformat()


def energy_to_number(value):
    mapping = {
        "Düşük": 1,
        "Orta": 2,
        "Yüksek": 3
    }
    return mapping.get(value, 0)


def compute_streak(routine_rows):
    if not routine_rows:
        return 0

    unique_dates = sorted({row["log_date"] for row in routine_rows}, reverse=True)
    if not unique_dates:
        return 0

    streak = 0
    current = date.fromisoformat(unique_dates[0])

    for d in unique_dates:
        parsed = date.fromisoformat(d)
        if parsed == current:
            streak += 1
            current = current.fromordinal(current.toordinal() - 1)
        else:
            break

    return streak


def build_routine_comment(last_routine):
    if not last_routine:
        return "Henüz routine kaydı yok. İlk kaydı girince günlük yorum burada görünecek."

    mood = last_routine["mood"]
    energy = last_routine["energy"]
    pain = last_routine["pain"]
    activity = last_routine["activity"]

    if mood == "Yorucuydu" or pain == "Belirgin":
        return f"Bugün {activity} tarafı biraz yük bindirmiş görünüyor. Yarın daha hafif tempo iyi olabilir."
    if mood == "İyiydi" and energy == "Yüksek":
        return f"{activity} günü verimli geçmiş görünüyor. Formun iyi, ritmi koru."
    if mood == "Normaldi" and pain == "Hafif":
        return f"Denge fena değil. {activity} sonrası kısa toparlanma iyi gelir."
    return f"Bugünkü {activity} kaydı alındı. Genel durum stabil görünüyor."


def build_winnie_comment(last_winnie):
    if not last_winnie:
        return "Henüz Winnie kaydı yok. İlk kayıt sonrası özet burada görünecek."

    appetite = last_winnie["appetite"]
    energy = last_winnie["energy"]
    toilet = last_winnie["toilet"]
    itch = last_winnie["itch"]

    if appetite == "Düşük" or toilet == "Problemli":
        return "Winnie tarafında dikkat gerektiren bir durum olabilir. İştah ve tuvaleti takip et."
    if itch == "Var":
        return "Kaşıma işareti var. Devam ederse notlarını karşılaştırmak faydalı olur."
    if appetite == "İyi" and energy in ("Normal", "Yüksek"):
        return "Winnie bugün keyifli görünüyor. Genel tablo iyi."
    return "Winnie tarafında durum normal görünüyor."


def vaccine_status(vaccine_rows):
    if not vaccine_rows:
        return {
            "title": "Aşı kaydı yok",
            "text": "Henüz aşı takvimi oluşturulmadı.",
            "level": "neutral"
        }

    upcoming = []
    today = date.today()

    for row in vaccine_rows:
        try:
            d = date.fromisoformat(row["vaccine_date"])
            delta = (d - today).days
            upcoming.append((delta, row))
        except ValueError:
            continue

    if not upcoming:
        return {
            "title": "Aşı tarihi okunamadı",
            "text": "Tarihlerde format sorunu olabilir.",
            "level": "neutral"
        }

    upcoming.sort(key=lambda x: x[0])
    delta, row = upcoming[0]

    if delta < 0:
        return {
            "title": "Aşı zamanı geçmiş",
            "text": f"{row['vaccine_name']} için tarih geçmiş görünüyor.",
            "level": "danger"
        }
    if delta <= 7:
        return {
            "title": "Aşı zamanı yaklaşıyor",
            "text": f"{row['vaccine_name']} için {delta} gün kaldı.",
            "level": "warning"
        }
    return {
        "title": "Sıradaki aşı planlandı",
        "text": f"{row['vaccine_name']} için {delta} gün var.",
        "level": "success"
    }


def get_finance_data():
    try:
        res = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=10)
        data = res.json()

        usd_try = data["rates"]["TRY"]
        eur_try = usd_try / data["rates"]["EUR"]
        gbp_try = usd_try / data["rates"]["GBP"]

        gram = round(usd_try * 0.55, 2)
        ceyrek = round(gram * 1.75, 2)
        tam = round(ceyrek * 4, 2)

        return {
            "usd": round(usd_try, 2),
            "eur": round(eur_try, 2),
            "gbp": round(gbp_try, 2),
            "gram": gram,
            "ceyrek": ceyrek,
            "tam": tam,
            "faiz": 42
        }
    except Exception as e:
        print("FINANCE ERROR:", e)
        return None


@app.route("/")
def index():
    conn = get_conn()
    cur = conn.cursor()

    routine_rows = cur.execute("""
        SELECT * FROM routine_logs
        ORDER BY log_date DESC, id DESC
    """).fetchall()

    winnie_rows = cur.execute("""
        SELECT * FROM winnie_logs
        ORDER BY log_date DESC, id DESC
    """).fetchall()

    vaccine_rows = cur.execute("""
        SELECT * FROM vaccine_logs
        ORDER BY vaccine_date ASC, id DESC
    """).fetchall()

    conn.close()

    last_routine = routine_rows[0] if routine_rows else None
    last_winnie = winnie_rows[0] if winnie_rows else None

    chart_source = list(reversed(routine_rows[:7]))
    chart_labels = [row["log_date"] for row in chart_source]
    chart_values = [energy_to_number(row["energy"]) for row in chart_source]

    finance = get_finance_data()

    streak = compute_streak(routine_rows)
    routine_comment = build_routine_comment(last_routine)
    winnie_comment = build_winnie_comment(last_winnie)
    vaccine_info = vaccine_status(vaccine_rows)

    return render_template(
        "dashboard.html",
        last_routine=last_routine,
        last_winnie=last_winnie,
        routine_rows=routine_rows[:10],
        winnie_rows=winnie_rows[:10],
        vaccine_rows=vaccine_rows,
        finance=finance,
        streak=streak,
        routine_comment=routine_comment,
        winnie_comment=winnie_comment,
        vaccine_info=vaccine_info,
        chart_labels=json.dumps(chart_labels, ensure_ascii=False),
        chart_values=json.dumps(chart_values),
        today_value=today_str()
    )


@app.route("/add_routine", methods=["POST"])
def add_routine():
    log_date = request.form.get("date") or today_str()
    mood = request.form.get("mood")
    energy = request.form.get("energy")
    pain = request.form.get("pain")
    activity = request.form.get("activity")
    note = request.form.get("note", "").strip()

    conn = get_conn()
    conn.execute("""
        INSERT INTO routine_logs (log_date, mood, energy, pain, activity, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        log_date,
        mood,
        energy,
        pain,
        activity,
        note,
        datetime.now().isoformat(timespec="seconds")
    ))
    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/add_winnie", methods=["POST"])
def add_winnie():
    log_date = request.form.get("date") or today_str()
    appetite = request.form.get("appetite")
    energy = request.form.get("energy")
    toilet = request.form.get("toilet")
    itch = request.form.get("itch")
    note = request.form.get("note", "").strip()

    conn = get_conn()
    conn.execute("""
        INSERT INTO winnie_logs (log_date, appetite, energy, toilet, itch, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        log_date,
        appetite,
        energy,
        toilet,
        itch,
        note,
        datetime.now().isoformat(timespec="seconds")
    ))
    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/add_vaccine", methods=["POST"])
def add_vaccine():
    vaccine_date = request.form.get("date")
    vaccine_name = request.form.get("name", "").strip()

    if vaccine_date and vaccine_name:
        conn = get_conn()
        conn.execute("""
            INSERT INTO vaccine_logs (vaccine_date, vaccine_name, created_at)
            VALUES (?, ?, ?)
        """, (
            vaccine_date,
            vaccine_name,
            datetime.now().isoformat(timespec="seconds")
        ))
        conn.commit()
        conn.close()

    return redirect("/")


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
