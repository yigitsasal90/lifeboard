from flask import Flask, render_template, request, redirect
import datetime
import requests

app = Flask(__name__)

routine_data = []
winnie_data = []
finance_data = []
vaccines = []

def get_finance_data():
    try:
        url = "https://api.exchangerate.host/latest?base=TRY"
        res = requests.get(url).json()

        usd = round(1 / res["rates"]["USD"], 2)
        eur = round(1 / res["rates"]["EUR"], 2)
        gbp = round(1 / res["rates"]["GBP"], 2)

        # Basit altın simülasyon (sonra gerçek API bağlarız)
        gram_altin = 2500 + (usd * 10)
        ceyrek = gram_altin * 1.75
        tam = gram_altin * 7

        faiz = 42.0  # Akbank referans

        return {
            "usd": usd,
            "eur": eur,
            "gbp": gbp,
            "gram": round(gram_altin, 2),
            "ceyrek": round(ceyrek, 2),
            "tam": round(tam, 2),
            "faiz": faiz
        }
    except:
        return None

@app.route("/")
def index():
    finance = get_finance_data()

    last_routine = routine_data[-1] if routine_data else None
    last_winnie = winnie_data[-1] if winnie_data else None

    return render_template(
        "dashboard.html",
        routine_data=routine_data,
        winnie_data=winnie_data,
        finance=finance,
        vaccines=vaccines,
        last_routine=last_routine,
        last_winnie=last_winnie
    )

@app.route("/add_routine", methods=["POST"])
def add_routine():
    routine_data.append({
        "date": request.form["date"],
        "energy": request.form["energy"],
        "pain": request.form["pain"],
        "activity": request.form["activity"],
        "note": request.form["note"]
    })
    return redirect("/")

@app.route("/add_winnie", methods=["POST"])
def add_winnie():
    winnie_data.append({
        "date": request.form["date"],
        "appetite": request.form["appetite"],
        "energy": request.form["energy"],
        "toilet": request.form["toilet"],
        "itch": request.form["itch"],
        "note": request.form["note"]
    })
    return redirect("/")

@app.route("/add_vaccine", methods=["POST"])
def add_vaccine():
    vaccines.append({
        "date": request.form["date"],
        "name": request.form["name"]
    })
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)
