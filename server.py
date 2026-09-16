"""
FANTAPROF — Backend Python + Supabase (opzionale, per persistenza reale)
========================================================================
Il frontend funziona da solo con localStorage. Questo server sostituisce
il salvataggio locale con un database Supabase reale.

SETUP:
  pip install flask flask-cors supabase

  Su supabase.com -> SQL Editor, esegui:

    create table users (
      id uuid default gen_random_uuid() primary key,
      username text unique not null,
      password text not null,
      credits int default 50,
      rosa int[] default '{}',
      punti int default 0
    );
    create table state (
      id int primary key,
      giornata int default 0,
      mercato_aperto boolean default true,
      prof_punti jsonb default '{}',
      eventi jsonb default '[]'
    );
    insert into state (id) values (1);

  Poi imposta le variabili d'ambiente:
    export SUPABASE_URL="https://xxxx.supabase.co"
    export SUPABASE_KEY="la-tua-anon-key"

  Avvio:  python server.py   (gira su http://localhost:5000)
"""
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client

app = Flask(__name__)
CORS(app)

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

MAX_CREDITS, MAX_ROSA = 50, 4


# ---------- AUTH ----------
@app.post("/api/register")
def register():
    d = request.get_json(force=True)
    username, password = (d.get("username") or "").strip(), d.get("password") or ""
    if len(username) < 3 or not password:
        return jsonify({"error": "Username o password non validi"}), 400
    existing = supabase.table("users").select("id").ilike("username", username).execute()
    if existing.data:
        return jsonify({"error": "Username già registrato"}), 409
    res = supabase.table("users").insert({
        "username": username, "password": password,
        "credits": MAX_CREDITS, "rosa": [], "punti": 0,
    }).execute()
    return jsonify({"ok": True, "user": res.data[0]})


@app.post("/api/login")
def login():
    d = request.get_json(force=True)
    res = (supabase.table("users").select("*")
           .ilike("username", (d.get("username") or "").strip())
           .eq("password", d.get("password") or "")
           .execute())
    if not res.data:
        return jsonify({"error": "Credenziali errate"}), 401
    return jsonify({"ok": True, "user": res.data[0]})


# ---------- MERCATO ----------
@app.post("/api/buy")
def buy():
    d = request.get_json(force=True)
    username, prof_id, costo = d["username"], int(d["prof_id"]), int(d["costo"])
    u = supabase.table("users").select("*").eq("username", username).single().execute().data
    if len(u["rosa"]) >= MAX_ROSA:
        return jsonify({"error": "Rosa al completo"}), 400
    if u["credits"] < costo:
        return jsonify({"error": "Crediti insufficienti"}), 400
    others = supabase.table("users").select("username,rosa").neq("username", username).execute()
    if any(prof_id in (o["rosa"] or []) for o in others.data):
        return jsonify({"error": "Prof già acquistata da un altro giocatore"}), 409
    supabase.table("users").update({
        "credits": u["credits"] - costo,
        "rosa": u["rosa"] + [prof_id],
    }).eq("username", username).execute()
    return jsonify({"ok": True})


@app.post("/api/sell")
def sell():
    d = request.get_json(force=True)
    username, prof_id, costo = d["username"], int(d["prof_id"]), int(d["costo"])
    u = supabase.table("users").select("*").eq("username", username).single().execute().data
    if prof_id not in (u["rosa"] or []):
        return jsonify({"error": "Prof non in rosa"}), 400
    supabase.table("users").update({
        "credits": u["credits"] + costo,
        "rosa": [p for p in u["rosa"] if p != prof_id],
    }).eq("username", username).execute()
    return jsonify({"ok": True})


# ---------- STATO GLOBALE (giornata, eventi, classifica) ----------
@app.get("/api/state")
def get_state():
    state = supabase.table("state").select("*").eq("id", 1).single().execute().data
    users = supabase.table("users").select("username,credits,rosa,punti").execute().data
    return jsonify({"state": state, "users": users})


@app.post("/api/simulate")
def simulate():
    """Salva l'esito di una giornata calcolata dal frontend (o da un cron)."""
    d = request.get_json(force=True)
    supabase.table("state").update({
        "giornata": d["giornata"],
        "prof_punti": d["prof_punti"],
        "eventi": d["eventi"][-100:],
    }).eq("id", 1).execute()
    for u in d["users"]:
        supabase.table("users").update({"punti": u["punti"]}).eq("username", u["username"]).execute()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
