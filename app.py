from flask import Flask, render_template, request, redirect
import json
import os
from datetime import datetime, date, timedelta

import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL eksik.")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def column_exists(conn, table_name, column_name):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            """,
            (table_name,)
        )
        cols = [r["column_name"] for r in cur.fetchall()]
    return column_name in cols


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS routine_logs (
                    id SERIAL PRIMARY KEY,
                    log_date TEXT NOT NULL,
                    flow TEXT,
                    mood TEXT,
                    energy TEXT NOT NULL,
                    pain TEXT NOT NULL,
                    activity TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS winnie_logs (
                    id SERIAL PRIMARY KEY,
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
                    id SERIAL PRIMARY KEY,
                    vaccine_date TEXT NOT NULL,
                    vaccine_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    note TEXT,
                    remind_date TEXT,
                    priority TEXT NOT NULL DEFAULT 'Normal',
                    is_done INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)

        if not column_exists(conn, "routine_logs", "flow"):
            with conn.cursor() as cur:
                cur.execute("ALTER TABLE routine_logs ADD COLUMN flow TEXT")

        if column_exists(conn, "routine_logs", "mood"):
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE routine_logs
                    SET flow = CASE
                        WHEN mood = 'İyiydi' THEN 'Rahattı'
                        WHEN mood = 'Normaldi' THEN 'Dengeliydi'
                        WHEN mood = 'Yorucuydu' THEN 'Zorladı'
                        ELSE COALESCE(flow, 'Dengeliydi')
                    END
                    WHERE flow IS NULL OR flow = ''
                """)

        conn.commit()


def today_str():
    return date.today().isoformat()


def safe_parse_date(value):
    try:
        return date.fromisoformat(value)
    except Exception:
        return None


def energy_to_number(value):
    return {
        "Düşük": 1,
        "Orta": 2,
        "Yüksek": 3
    }.get(value, 0)


def calculate_streak(routine_rows):
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


def routine_trend(row):
    if not row:
        return {"label": "Veri yok", "class": "neutral"}

    if row["flow"] == "Rahattı" and row["energy"] == "Yüksek":
        return {"label": "Formda", "class": "good"}

    if row["flow"] == "Zorladı" or row["pain"] == "Belirgin":
        return {"label": "Yüksek yük", "class": "bad"}

    return {"label": "Dengeli", "class": "mid"}


def winnie_trend(row):
    if not row:
        return {"label": "Veri yok", "class": "neutral"}

    if row["appetite"] == "İyi" and row["toilet"] == "Normal" and row["itch"] == "Yok":
        return {"label": "Keyfi yerinde", "class": "good"}

    if row["appetite"] == "Düşük" or row["toilet"] == "Problemli":
        return {"label": "Dikkat et", "class": "bad"}

    return {"label": "Takipte", "class": "mid"}


def build_routine_comment(rows):
    if not rows:
        return "Henüz routine kaydı yok. İlk kayıt girince günlük yorum burada görünecek."

    latest = rows[0]
    latest3 = rows[:3]

    hard_days = sum(1 for r in latest3 if r["flow"] == "Zorladı" or r["pain"] == "Belirgin")
    high_energy = sum(1 for r in latest3 if r["energy"] == "Yüksek")
    low_energy = sum(1 for r in latest3 if r["energy"] == "Düşük")

    if hard_days >= 2:
        return "Son günlerde yük artmış görünüyor. Bir toparlanma günü eklemek iyi olabilir."

    if high_energy >= 2 and latest["flow"] == "Rahattı":
        return "Ritmin iyi. Son kayıtlar formunun yukarı gittiğini gösteriyor."

    if low_energy >= 2:
        return "Enerji biraz aşağıda seyrediyor. Uyku, beslenme ve yoğunluğu gözden geçirmek iyi olabilir."

    if latest["activity"] in ("Padel", "Futbol") and latest["pain"] == "Hafif":
        return f"{latest['activity']} sonrası hafif yük var. Kısa toparlanma iyi gelebilir."

    return f"Bugünkü {latest['activity']} kaydı alındı. Genel görünüm dengeli."


def build_winnie_comment(rows):
    if not rows:
        return "Henüz Winnie kaydı yok. İlk kayıt sonrası özet burada görünecek."

    latest = rows[0]
    latest3 = rows[:3]

    issue_count = sum(
        1 for r in latest3
        if r["appetite"] == "Düşük" or r["toilet"] == "Problemli" or r["itch"] == "Var"
    )

    if issue_count >= 2:
        return "Son kayıtlarda dikkat gerektiren işaretler var. Winnie’yi biraz daha yakından takip etmek iyi olabilir."

    if latest["appetite"] == "İyi" and latest["energy"] in ("Normal", "Yüksek") and latest["toilet"] == "Normal":
        return "Winnie’nin genel tablosu iyi görünüyor. İştah ve enerji tarafı dengeli."

    if latest["itch"] == "Var":
        return "Kaşıma işareti var. Devam ederse zamanlamasını ve sıklığını not etmek faydalı olur."

    return "Winnie tarafında genel durum stabil görünüyor."


def vaccine_status(vaccine_rows):
    if not vaccine_rows:
        return {
            "title": "Aşı kaydı yok",
            "text": "Henüz aşı takvimi oluşturulmadı.",
            "level": "neutral",
            "badge": None
        }

    upcoming = []
    today = date.today()

    for row in vaccine_rows:
        d = safe_parse_date(row["vaccine_date"])
        if not d:
            continue
        delta = (d - today).days
        upcoming.append((delta, row))

    if not upcoming:
        return {
            "title": "Aşı tarihi okunamadı",
            "text": "Tarihlerde format sorunu olabilir.",
            "level": "neutral",
            "badge": None
        }

    upcoming.sort(key=lambda x: x[0])
    delta, row = upcoming[0]

    if delta < 0:
        return {
            "title": "Aşı zamanı geçmiş",
            "text": f"{row['vaccine_name']} için tarih geçmiş görünüyor.",
            "level": "danger",
            "badge": "Geçmiş"
        }

    if delta <= 7:
        return {
            "title": "Aşı zamanı yaklaşıyor",
            "text": f"{row['vaccine_name']} için {delta} gün kaldı.",
            "level": "warning",
            "badge": f"{delta} gün"
        }

    return {
        "title": "Sıradaki aşı planlandı",
        "text": f"{row['vaccine_name']} için {delta} gün var.",
        "level": "success",
        "badge": None
    }


def calculate_daily_score(routine_rows, winnie_rows, vaccine_info):
    score = 40

    if routine_rows:
        latest = routine_rows[0]

        if latest["flow"] == "Rahattı":
            score += 15
        elif latest["flow"] == "Dengeliydi":
            score += 8
        else:
            score -= 8

        if latest["energy"] == "Yüksek":
            score += 18
        elif latest["energy"] == "Orta":
            score += 10
        else:
            score -= 6

        if latest["pain"] == "Yok":
            score += 12
        elif latest["pain"] == "Hafif":
            score += 5
        else:
            score -= 8

        if latest["activity"] in ("Padel", "Futbol", "Fonksiyonel Antrenman"):
            score += 8
        elif latest["activity"] in ("Yürüyüş", "E-Scooter", "Direnç Bandı"):
            score += 4

    if winnie_rows:
        latest_w = winnie_rows[0]

        if latest_w["appetite"] == "İyi":
            score += 5
        elif latest_w["appetite"] == "Düşük":
            score -= 4

        if latest_w["toilet"] == "Problemli":
            score -= 5

        if latest_w["itch"] == "Var":
            score -= 3

    if vaccine_info["level"] == "warning":
        score -= 3
    elif vaccine_info["level"] == "danger":
        score -= 7

    score = max(0, min(score, 100))

    if score >= 80:
        text = "Harika gidiyorsun, devam et!"
    elif score >= 60:
        text = "İyi ama geliştirilebilir."
    elif score >= 45:
        text = "Fena değil, biraz toparlama iyi gelir."
    else:
        text = "Düşüş var, dinlenme ve düzen önemli."

    return score, text


def get_last_7_days(rows, date_key):
    today = date.today()
    result = []
    for row in rows:
        d = safe_parse_date(row[date_key])
        if not d:
            continue
        if (today - d).days <= 6:
            result.append(row)
    return result


def build_weekly_stats(routine_rows, winnie_rows, reminder_rows):
    routine_7 = get_last_7_days(routine_rows, "log_date")
    winnie_7 = get_last_7_days(winnie_rows, "log_date")

    active_days = len({r["log_date"] for r in routine_7})
    avg_energy_num = 0
    if routine_7:
        avg_energy_num = round(sum(energy_to_number(r["energy"]) for r in routine_7) / len(routine_7), 2)

    energy_text = "Veri yok"
    if avg_energy_num > 0:
        if avg_energy_num < 1.7:
            energy_text = "Düşük"
        elif avg_energy_num < 2.4:
            energy_text = "Orta"
        else:
            energy_text = "Yüksek"

    activity_count = {}
    for r in routine_7:
        activity_count[r["activity"]] = activity_count.get(r["activity"], 0) + 1

    top_activity = max(activity_count, key=activity_count.get) if activity_count else "Yok"

    good_days = sum(1 for r in routine_7 if r["flow"] == "Rahattı")
    mid_days = sum(1 for r in routine_7 if r["flow"] == "Dengeliydi")
    hard_days = sum(1 for r in routine_7 if r["flow"] == "Zorladı")

    winnie_stable = sum(
        1 for r in winnie_7
        if r["appetite"] == "İyi" and r["toilet"] == "Normal" and r["itch"] == "Yok"
    )

    open_reminders = sum(1 for r in reminder_rows if r["is_done"] == 0)

    return {
        "active_days": active_days,
        "energy_text": energy_text,
        "top_activity": top_activity,
        "good_days": good_days,
        "mid_days": mid_days,
        "hard_days": hard_days,
        "winnie_stable": winnie_stable,
        "open_reminders": open_reminders
    }


def build_life_summary(last_routine, last_winnie, vaccine_info, weekly_stats):
    parts = []

    if last_routine:
        parts.append(f"Routine tarafında son görünüm {last_routine['flow'].lower()}.")

    if last_winnie:
        if last_winnie["appetite"] == "İyi" and last_winnie["toilet"] == "Normal":
            parts.append("Winnie genel olarak stabil görünüyor.")
        else:
            parts.append("Winnie tarafında takip gerektiren küçük işaretler olabilir.")

    if weekly_stats["active_days"] >= 4:
        parts.append("Bu hafta hareket ritmin iyi gidiyor.")
    elif weekly_stats["active_days"] >= 2:
        parts.append("Bu hafta orta tempoda gidiyorsun.")
    else:
        parts.append("Bu hafta biraz daha düzenli kayıt girmek iyi olabilir.")

    if vaccine_info["level"] == "warning":
        parts.append("Yaklaşan aşı tarihi için hazırlık yapmayı unutma.")

    if weekly_stats["open_reminders"] > 0:
        parts.append(f"Açıkta {weekly_stats['open_reminders']} hatırlatma var.")

    return " ".join(parts)


def classify_reminder(remind_date, is_done):
    if is_done:
        return "done"

    if not remind_date:
        return "normal"

    d = safe_parse_date(remind_date)
    if not d:
        return "normal"

    today = date.today()
    delta = (d - today).days

    if delta < 0:
        return "overdue"
    if delta <= 2:
        return "soon"
    return "normal"


def reminder_filter_match(reminder, active_filter):
    d = safe_parse_date(reminder["remind_date"]) if reminder["remind_date"] else None
    today = date.today()

    if active_filter == "today":
        return d == today and reminder["is_done"] == 0

    if active_filter == "week":
        if reminder["is_done"] == 1 or not d:
            return False
        return today <= d <= (today + timedelta(days=6))

    if active_filter == "done":
        return reminder["is_done"] == 1

    return True


def decorate_reminders(reminder_rows, active_filter="all"):
    decorated = []
    overdue_count = 0

    for r in reminder_rows:
        state_class = classify_reminder(r["remind_date"], r["is_done"])
        if state_class == "overdue":
            overdue_count += 1

        item = {
            "id": r["id"],
            "title": r["title"],
            "note": r["note"],
            "remind_date": r["remind_date"],
            "priority": r["priority"],
            "is_done": r["is_done"],
            "state_class": state_class
        }

        if reminder_filter_match(item, active_filter):
            decorated.append(item)

    return decorated, overdue_count


# -----------------------------
# ROUTES
# -----------------------------
@app.route("/")
def index():
    active_reminder_filter = request.args.get("reminder_filter", "all")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM routine_logs
                ORDER BY log_date DESC, id DESC
            """)
            routine_rows = cur.fetchall()

            cur.execute("""
                SELECT * FROM winnie_logs
                ORDER BY log_date DESC, id DESC
            """)
            winnie_rows = cur.fetchall()

            cur.execute("""
                SELECT * FROM vaccine_logs
                ORDER BY vaccine_date ASC, id DESC
            """)
            vaccine_rows = cur.fetchall()

            cur.execute("""
                SELECT * FROM reminders
                ORDER BY is_done ASC, remind_date IS NULL, remind_date ASC, id DESC
            """)
            reminder_rows = cur.fetchall()

    last_routine = routine_rows[0] if routine_rows else None
    last_winnie = winnie_rows[0] if winnie_rows else None

    chart_source = list(reversed(routine_rows[:30]))
    chart_labels = [row["log_date"] for row in chart_source]
    chart_values = [energy_to_number(row["energy"]) for row in chart_source]

    vaccine_info = vaccine_status(vaccine_rows)
    streak = calculate_streak(routine_rows)
    score, score_text = calculate_daily_score(routine_rows, winnie_rows, vaccine_info)
    weekly_stats = build_weekly_stats(routine_rows, winnie_rows, reminder_rows)
    life_summary = build_life_summary(last_routine, last_winnie, vaccine_info, weekly_stats)

    reminders, overdue_count = decorate_reminders(reminder_rows, active_reminder_filter)

    edit_reminder_id = request.args.get("edit_reminder")
    edit_reminder = None
    if edit_reminder_id:
        try:
            edit_reminder_id = int(edit_reminder_id)
            for item in reminder_rows:
                if item["id"] == edit_reminder_id:
                    edit_reminder = item
                    break
        except ValueError:
            edit_reminder = None

    return render_template(
        "dashboard.html",
        last_routine=last_routine,
        last_winnie=last_winnie,
        routine_rows=routine_rows,
        winnie_rows=winnie_rows,
        vaccine_rows=vaccine_rows,
        reminders=reminders,
        streak=streak,
        score=score,
        score_text=score_text,
        routine_comment=build_routine_comment(routine_rows),
        winnie_comment=build_winnie_comment(winnie_rows),
        vaccine_info=vaccine_info,
        routine_trend=routine_trend(last_routine),
        winnie_trend=winnie_trend(last_winnie),
        chart_labels=json.dumps(chart_labels, ensure_ascii=False),
        chart_values=json.dumps(chart_values),
        today_value=today_str(),
        weekly_stats=weekly_stats,
        life_summary=life_summary,
        overdue_count=overdue_count,
        active_reminder_filter=active_reminder_filter,
        edit_reminder=edit_reminder
    )


@app.route("/add_routine", methods=["POST"])
def add_routine():
    log_date = request.form.get("date") or today_str()
    flow = request.form.get("flow")
    energy = request.form.get("energy")
    pain = request.form.get("pain")
    activity = request.form.get("activity")
    note = request.form.get("note", "").strip()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO routine_logs (log_date, flow, energy, pain, activity, note, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                log_date,
                flow,
                energy,
                pain,
                activity,
                note,
                datetime.now().isoformat(timespec="seconds")
            ))
        conn.commit()

    return redirect("/")


@app.route("/add_winnie", methods=["POST"])
def add_winnie():
    log_date = request.form.get("date") or today_str()
    appetite = request.form.get("appetite")
    energy = request.form.get("energy")
    toilet = request.form.get("toilet")
    itch = request.form.get("itch")
    note = request.form.get("note", "").strip()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO winnie_logs (log_date, appetite, energy, toilet, itch, note, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
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

    return redirect("/")


@app.route("/add_vaccine", methods=["POST"])
def add_vaccine():
    vaccine_date = request.form.get("date")
    vaccine_name = request.form.get("name", "").strip()

    if vaccine_date and vaccine_name:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO vaccine_logs (vaccine_date, vaccine_name, created_at)
                    VALUES (%s, %s, %s)
                """, (
                    vaccine_date,
                    vaccine_name,
                    datetime.now().isoformat(timespec="seconds")
                ))
            conn.commit()

    return redirect("/")


@app.route("/add_reminder", methods=["POST"])
def add_reminder():
    title = request.form.get("title", "").strip()
    note = request.form.get("note", "").strip()
    remind_date = request.form.get("remind_date", "").strip()
    priority = request.form.get("priority", "Normal").strip()

    if title:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO reminders (title, note, remind_date, priority, is_done, created_at)
                    VALUES (%s, %s, %s, %s, 0, %s)
                """, (
                    title,
                    note,
                    remind_date if remind_date else None,
                    priority,
                    datetime.now().isoformat(timespec="seconds")
                ))
            conn.commit()

    return redirect("/")


@app.route("/update_reminder/<int:reminder_id>", methods=["POST"])
def update_reminder(reminder_id):
    title = request.form.get("title", "").strip()
    note = request.form.get("note", "").strip()
    remind_date = request.form.get("remind_date", "").strip()
    priority = request.form.get("priority", "Normal").strip()

    if title:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE reminders
                    SET title = %s,
                        note = %s,
                        remind_date = %s,
                        priority = %s
                    WHERE id = %s
                """, (
                    title,
                    note,
                    remind_date if remind_date else None,
                    priority,
                    reminder_id
                ))
            conn.commit()

    return redirect("/")


@app.route("/toggle_reminder/<int:reminder_id>", methods=["POST"])
def toggle_reminder(reminder_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT is_done FROM reminders WHERE id = %s", (reminder_id,))
            row = cur.fetchone()

            if row:
                new_val = 0 if row["is_done"] == 1 else 1
                cur.execute(
                    "UPDATE reminders SET is_done = %s WHERE id = %s",
                    (new_val, reminder_id)
                )
        conn.commit()

    return redirect("/")


@app.route("/delete_reminder/<int:reminder_id>", methods=["POST"])
def delete_reminder(reminder_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM reminders WHERE id = %s", (reminder_id,))
        conn.commit()
    return redirect("/")


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
