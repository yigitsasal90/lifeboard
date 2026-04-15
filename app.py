from flask import Flask, render_template, request, redirect
import json
import os
import requests

app = Flask(__name__)

DATA_FILE = "data.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {"routine": [], "winnie": [], "vaccines": []}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


def get_finance_data():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        res = requests.get(url)
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
    data = load_data()

    finance = get_finance_data()

    return render_template(
        "dashboard.html",
        last_routine=data["routine"][-1] if data["routine"] else None,
        last_winnie=data["winnie"][-1] if data["winnie"] else None,
        vaccines=data["vaccines"],
        finance=finance
    )


@app.route("/add_routine", methods=["POST"])
def add_routine():
    data = load_data()

    new_entry = {
        "date": request.form["date"],
        "energy": request.form["energy"],
        "pain": request.form["pain"],
        "activity": request.form["activity"],
        "note": request.form["note"]
    }

    data["routine"].append(new_entry)
    save_data(data)

    return redirect("/")


@app.route("/add_winnie", methods=["POST"])
def add_winnie():
    data = load_data()

    new_entry = {
        "date": request.form["date"],
        "appetite": request.form["appetite"],
        "energy": request.form["energy"],
        "toilet": request.form["toilet"],
        "itch": request.form["itch"],
        "note": request.form["note"]
    }

    data["winnie"].append(new_entry)
    save_data(data)

    return redirect("/")


@app.route("/add_vaccine", methods=["POST"])
def add_vaccine():
    data = load_data()

    new_entry = {
        "date": request.form["date"],
        "name": request.form["name"]
    }

    data["vaccines"].append(new_entry)
    save_data(data)

    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True)
