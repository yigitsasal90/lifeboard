from flask import Flask, render_template, request, redirect
import sqlite3
import os
import json
import requests
import csv
import io
from datetime import datetime, date

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
            flow TEXT NOT NULL,
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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS finance_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def today_str():
    return date.today().isoformat()


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
        elif latest["activity"] in ("Yürüyüş", "E-Scooter"):
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


def http_get_json(url, headers=None, timeout=15):
    response = requests.get(url, headers=headers or {}, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_alpha_fx(from_currency, to_currency, api_key):
    url = (
        "https://www.alphavantage.co/query"
        f"?function=CURRENCY_EXCHANGE_RATE&from_currency={from_currency}"
        f"&to_currency={to_currency}&apikey={api_key}"
    )
    data = http_get_json(url)
    quote = data.get("Realtime Currency Exchange Rate", {})
    value = quote.get("5. Exchange Rate")
    refreshed = quote.get("6. Last Refreshed")
    if value is None:
        raise ValueError(f"FX data missing for {from_currency}/{to_currency}")
    return float(value), refreshed


def fetch_brent(api_key):
    url = (
        "https://www.alphavantage.co/query"
        f"?function=BRENT&interval=daily&datatype=csv&apikey={api_key}"
    )
    response = requests.get(url, timeout=20)
    response.raise_for_status()

    reader = csv.DictReader(io.StringIO(response.text))
    rows = list(reader)

    if not rows:
        raise ValueError("BRENT CSV boş döndü")

    latest = rows[0]

    # Alpha Vantage commodity CSV'lerinde genelde "value" kolonu olur
    possible_value_keys = ["value", "Value", "close", "Close"]
    value = None
    for key in possible_value_keys:
        if key in latest and latest[key]:
            value = float(latest[key])
            break

    if value is None:
        raise ValueError("BRENT değeri çözümlenemedi")

    timestamp = latest.get("timestamp") or latest.get("date") or datetime.now().isoformat()
    return value, timestamp


def fetch_gold_prices_try(metals_api_key, usd_try):
    url = f"https://metals-api.com/api/latest?access_key={metals_api_key}&base=USD&symbols=XAU"
    data = http_get_json(url)

    rates = data.get("rates", {})
    xau_value = rates.get("XAU")

    if xau_value is None:
        raise ValueError("XAU değeri bulunamadı")

    xau_usd_per_ounce = float(xau_value)

    # Bazı metal API'lerinde yön ters olabiliyor; küçük sayı dönerse çevir
    if xau_usd_per_ounce < 100:
        xau_usd_per_ounce = 1 / xau_usd_per_ounce

    gram_try = (xau_usd_per_ounce * usd_try) / 31.1034768

    # Türkiye piyasasına daha yakın yaklaşık katsayılar
    ceyrek_try = gram_try * 1.62
    tam_try = ceyrek_try * 4

    return {
        "gram": round(gram_try, 2),
        "ceyrek": round(ceyrek_try, 2),
        "tam": round(tam_try, 2),
        "timestamp": data.get("date") or datetime.now().isoformat()
    }


def get_last_finance_snapshot():
    conn = get_conn()
    row = conn.execute("""
        SELECT * FROM finance_snapshots
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()
    conn.close()

    if not row:
        return None

    return {
        "fetched_at": row["fetched_at"],
        "payload": json.loads(row["payload_json"])
    }


def save_finance_snapshot(payload):
    conn = get_conn()
    conn.execute("""
        INSERT INTO finance_snapshots (fetched_at, payload_json)
        VALUES (?, ?)
    """, (
        datetime.now().isoformat(timespec="seconds"),
        json.dumps(payload, ensure_ascii=False)
    ))
    conn.commit()
    conn.close()


def should_save_new_snapshot(last_snapshot):
    if not last_snapshot:
        return True

    try:
        last_time = datetime.fromisoformat(last_snapshot["fetched_at"])
    except ValueError:
        return True

    diff = datetime.now() - last_time
    return diff.total_seconds() >= 55


def build_finance_cards(current_values, previous_values=None):
    labels = {
        "usd": "Dolar",
        "eur": "Euro",
        "gbp": "Sterlin",
        "gram": "Gram Altın",
        "ceyrek": "Çeyrek Altın",
        "tam": "Tam Altın",
        "brent": "Brent Petrol",
        "faiz": "Akbank Faiz"
    }

    cards = []

    for key in ["usd", "eur", "gbp", "gram", "ceyrek", "tam", "brent", "faiz"]:
        value = current_values.get(key)
        prev = previous_values.get(key) if previous_values else None

        arrow = "•"
        change_text = "İlk veri"
        change_class = "flat"

        if prev is not None and prev != 0:
            diff = value - prev
            pct = (diff / prev) * 100

            if diff > 0:
                arrow = "▲"
                change_class = "up"
            elif diff < 0:
                arrow = "▼"
                change_class = "down"
            else:
                arrow = "•"
                change_class = "flat"

            sign = "+" if pct > 0 else ""
            change_text = f"{sign}{pct:.2f}%"

        cards.append({
            "key": key,
            "label": labels[key],
            "value": value,
            "display_value": f"%{value:.2f}" if key == "faiz" else f"{value:.2f}",
            "arrow": arrow,
            "change_text": change_text,
            "change_class": change_class
        })

    return cards


def fetch_live_finance():
    alpha_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    metals_key = os.environ.get("METALS_API_KEY", "").strip()

    if not alpha_key or not metals_key:
        return None, "API key eksik"

    try:
        usd_try, fx_time = fetch_alpha_fx("USD", "TRY", alpha_key)
        eur_try, _ = fetch_alpha_fx("EUR", "TRY", alpha_key)
        gbp_try, _ = fetch_alpha_fx("GBP", "TRY", alpha_key)
        brent, brent_time = fetch_brent(alpha_key)
        gold = fetch_gold_prices_try(metals_key, usd_try)

        values = {
            "usd": round(usd_try, 2),
            "eur": round(eur_try, 2),
            "gbp": round(gbp_try, 2),
            "gram": gold["gram"],
            "ceyrek": gold["ceyrek"],
            "tam": gold["tam"],
            "brent": round(brent, 2),
            "faiz": 42.00
        }

        updated_at = fx_time or brent_time or gold["timestamp"] or datetime.now().isoformat()

        return {
            "values": values,
            "updated_at": updated_at
        }, None

    except Exception as e:
        print("FINANCE ERROR:", e)
        return None, str(e)


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

    chart_source = list(reversed(routine_rows[:30]))
    chart_labels = [row["log_date"] for row in chart_source]
    chart_values = [energy_to_number(row["energy"]) for row in chart_source]

    vaccine_info = vaccine_status(vaccine_rows)
    streak = calculate_streak(routine_rows)
    score, score_text = calculate_daily_score(routine_rows, winnie_rows, vaccine_info)

    live_finance, finance_error = fetch_live_finance()
    last_snapshot = get_last_finance_snapshot()

    finance_cards = []
    finance_updated_at = None

    if live_finance:
        previous_values = last_snapshot["payload"]["values"] if last_snapshot else None
        finance_cards = build_finance_cards(live_finance["values"], previous_values)
        finance_updated_at = live_finance["updated_at"]

        if should_save_new_snapshot(last_snapshot):
            save_finance_snapshot(live_finance)
    elif last_snapshot:
        finance_cards = build_finance_cards(last_snapshot["payload"]["values"], None)
        finance_updated_at = f"{last_snapshot['fetched_at']} (son başarılı veri)"
    else:
        finance_cards = []

    return render_template(
        "dashboard.html",
        last_routine=last_routine,
        last_winnie=last_winnie,
        routine_rows=routine_rows,
        winnie_rows=winnie_rows,
        vaccine_rows=vaccine_rows,
        finance_cards=finance_cards,
        finance_updated_at=finance_updated_at,
        finance_error=finance_error,
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
        today_value=today_str()
    )


@app.route("/add_routine", methods=["POST"])
def add_routine():
    log_date = request.form.get("date") or today_str()
    flow = request.form.get("flow")
    energy = request.form.get("energy")
    pain = request.form.get("pain")
    activity = request.form.get("activity")
    note = request.form.get("note", "").strip()

    conn = get_conn()
    conn.execute("""
        INSERT INTO routine_logs (log_date, flow, energy, pain, activity, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
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
