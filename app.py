import os
import json
import secrets
import requests
from functools import wraps
from flask import (
    Flask, redirect, request, session,
    jsonify, render_template, url_for, abort
)

# ─────────────────────────────────────────────
#  КОНФІГ
# ─────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

CLIENT_ID     = os.getenv("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
BOT_TOKEN     = os.getenv("DISCORD_BOT_TOKEN")
SECRET_KEY    = os.getenv("SECRET_KEY", secrets.token_hex(32))
REDIRECT_URI  = os.getenv("REDIRECT_URI", "http://localhost:5000/callback")

DISCORD_API = "https://discord.com/api/v10"
OAUTH_URL   = "https://discord.com/oauth2/authorize"
TOKEN_URL   = f"{DISCORD_API}/oauth2/token"
SCOPES      = "identify guilds"

app = Flask(__name__)
app.secret_key = "raven-super-secret-key-do-not-change"
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"]   = os.getenv("RAILWAY_ENVIRONMENT") is not None
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = 600

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def discord_get(endpoint, token):
    r = requests.get(f"{DISCORD_API}{endpoint}",
        headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    return r.json()

def bot_get(endpoint):
    r = requests.get(f"{DISCORD_API}{endpoint}",
        headers={"Authorization": f"Bot {BOT_TOKEN}"}, timeout=10)
    if r.status_code == 404: return None
    if r.status_code == 403: return {"error": "forbidden"}
    r.raise_for_status()
    return r.json()

def bot_post(endpoint, payload=None):
    r = requests.post(f"{DISCORD_API}{endpoint}",
        headers={"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"},
        json=payload or {}, timeout=10)
    r.raise_for_status()
    return r.json() if r.content else {}

def bot_patch(endpoint, payload):
    r = requests.patch(f"{DISCORD_API}{endpoint}",
        headers={"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"},
        json=payload, timeout=10)
    r.raise_for_status()
    return r.json() if r.content else {}

def bot_delete(endpoint):
    r = requests.delete(f"{DISCORD_API}{endpoint}",
        headers={"Authorization": f"Bot {BOT_TOKEN}"}, timeout=10)
    return r.status_code in (200, 204)

def bot_put(endpoint, payload=None):
    r = requests.put(f"{DISCORD_API}{endpoint}",
        headers={"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"},
        json=payload or {}, timeout=10)
    r.raise_for_status()
    return r.json() if r.content else {}

def get_managed_guilds(user_guilds):
    ADMIN        = 0x8
    MANAGE_GUILD = 0x20
    return [g for g in user_guilds if
            g.get("owner") or
            (int(g.get("permissions", 0)) & ADMIN) or
            (int(g.get("permissions", 0)) & MANAGE_GUILD)]

def get_bot_guild_ids():
    data = bot_get("/users/@me/guilds")
    return {g["id"] for g in (data or [])}

def guild_icon_url(g):
    if g.get("icon"):
        ext = "gif" if g["icon"].startswith("a_") else "png"
        return f"https://cdn.discordapp.com/icons/{g['id']}/{g['icon']}.{ext}"
    return None

def user_avatar_url(u):
    if u.get("avatar"):
        return f"https://cdn.discordapp.com/avatars/{u['id']}/{u['avatar']}.png"
    return f"https://cdn.discordapp.com/embed/avatars/{int(u.get('discriminator',0) or 0) % 5}.png"

def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated

# ─────────────────────────────────────────────
#  PAGE ROUTES
# ─────────────────────────────────────────────
@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("servers"))
    return render_template("index.html", client_id=CLIENT_ID)

@app.route("/login")
def login():
    session.permanent = True
    params = {
        "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI,
        "response_type": "code", "scope": SCOPES,
        "prompt": "none",
    }
    url = OAUTH_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return redirect(url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return redirect(url_for("login"))
    r = requests.post(TOKEN_URL, data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT_URI,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10)
    r.raise_for_status()
    tokens = r.json()
    user = discord_get("/users/@me", tokens["access_token"])
    user["avatar_url"] = user_avatar_url(user)
    session["user"] = user
    session["access_token"] = tokens["access_token"]
    return redirect(url_for("servers"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/servers")
@require_login
def servers():
    return render_template("servers.html", user=session["user"], client_id=CLIENT_ID)

@app.route("/dashboard/<guild_id>")
@require_login
def dashboard(guild_id):
    return render_template("dashboard.html", user=session["user"],
                           guild_id=guild_id, client_id=CLIENT_ID)

# ─────────────────────────────────────────────
#  API — SERVERS
# ─────────────────────────────────────────────
@app.route("/api/servers")
@require_login
def api_servers():
    try:
        all_guilds  = discord_get("/users/@me/guilds", session["access_token"])
        managed     = get_managed_guilds(all_guilds)
        bot_ids     = get_bot_guild_ids()
        return jsonify([{
            "id": g["id"], "name": g["name"],
            "icon": guild_icon_url(g),
            "owner": g.get("owner", False),
            "bot_added": g["id"] in bot_ids,
        } for g in managed])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/me")
@require_login
def api_me():
    return jsonify(session["user"])

# ─────────────────────────────────────────────
#  API — GUILD INFO
# ─────────────────────────────────────────────
@app.route("/api/guild/<gid>")
@require_login
def api_guild(gid):
    try:
        g = bot_get(f"/guilds/{gid}?with_counts=true")
        if not g or "error" in g:
            return jsonify({"error": "Bot not in guild or forbidden"}), 404
        return jsonify({
            "id": g["id"], "name": g["name"],
            "icon": guild_icon_url(g),
            "member_count":  g.get("approximate_member_count", 0),
            "online_count":  g.get("approximate_presence_count", 0),
            "channel_count": len(g.get("channels", [])),
            "role_count":    len(g.get("roles", [])),
            "boost_level":   g.get("premium_tier", 0),
            "boost_count":   g.get("premium_subscription_count", 0),
            "owner_id":      g.get("owner_id"),
            "description":   g.get("description") or "",
            "verification_level": g.get("verification_level", 0),
            "created_at": str(int(g["id"]) >> 22) + "ms",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# NEW: Розгорнута статистика для overview
@app.route("/api/guild/<gid>/stats")
@require_login
def api_guild_stats(gid):
    try:
        g        = bot_get(f"/guilds/{gid}?with_counts=true") or {}
        roles    = bot_get(f"/guilds/{gid}/roles") or []
        channels = bot_get(f"/guilds/{gid}/channels") or []
        bans     = bot_get(f"/guilds/{gid}/bans") or []
        ch_types = {}
        for c in channels:
            t = c.get("type", 0)
            ch_types[t] = ch_types.get(t, 0) + 1
        return jsonify({
            "members":     g.get("approximate_member_count", 0),
            "online":      g.get("approximate_presence_count", 0),
            "roles":       len([r for r in roles if r["name"] != "@everyone"]),
            "bans":        len(bans),
            "channels":    len(channels),
            "text_ch":     ch_types.get(0, 0),
            "voice_ch":    ch_types.get(2, 0),
            "category_ch": ch_types.get(4, 0),
            "boost_level": g.get("premium_tier", 0),
            "boost_count": g.get("premium_subscription_count", 0),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────
#  API — CHANNELS
# ─────────────────────────────────────────────
@app.route("/api/guild/<gid>/channels")
@require_login
def api_channels(gid):
    try:
        channels = bot_get(f"/guilds/{gid}/channels") or []
        return jsonify([
            {"id": c["id"], "name": c["name"], "type": c["type"],
             "position": c.get("position", 0), "topic": c.get("topic") or "",
             "nsfw": c.get("nsfw", False), "parent_id": c.get("parent_id")}
            for c in channels
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/guild/<gid>/channels", methods=["POST"])
@require_login
def api_create_channel(gid):
    b = request.get_json()
    name = b.get("name", "").strip().replace(" ", "-").lower()
    if not name:
        return jsonify({"error": "Потрібна назва каналу"}), 400
    try:
        ch = bot_post(f"/guilds/{gid}/channels", {
            "name": name, "type": b.get("type", 0),
            "topic": b.get("topic", ""),
        })
        return jsonify({"ok": True, "channel": ch})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/guild/<gid>/channels/<cid>", methods=["DELETE"])
@require_login
def api_delete_channel(gid, cid):
    try:
        ok = bot_delete(f"/channels/{cid}")
        return jsonify({"ok": ok})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────
#  API — ROLES
# ─────────────────────────────────────────────
@app.route("/api/guild/<gid>/roles")
@require_login
def api_roles(gid):
    try:
        roles = bot_get(f"/guilds/{gid}/roles") or []
        return jsonify([
            {"id": r["id"], "name": r["name"], "color": r["color"],
             "position": r["position"], "managed": r.get("managed", False),
             "mentionable": r.get("mentionable", False),
             "permissions": r.get("permissions", "0")}
            for r in roles if r["name"] != "@everyone"
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/guild/<gid>/roles", methods=["POST"])
@require_login
def api_create_role(gid):
    b = request.get_json()
    name = b.get("name", "").strip()
    if not name:
        return jsonify({"error": "Потрібна назва ролі"}), 400
    try:
        role = bot_post(f"/guilds/{gid}/roles", {
            "name": name,
            "color": int(b.get("color", "5865f2").lstrip("#"), 16),
            "mentionable": b.get("mentionable", False),
        })
        return jsonify({"ok": True, "role": role})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# NEW: Видалення ролі
@app.route("/api/guild/<gid>/roles/<rid>", methods=["DELETE"])
@require_login
def api_delete_role(gid, rid):
    try:
        ok = bot_delete(f"/guilds/{gid}/roles/{rid}")
        return jsonify({"ok": ok})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────
#  API — MEMBERS (пошук + пагінація)
# ─────────────────────────────────────────────
@app.route("/api/guild/<gid>/members")
@require_login
def api_members(gid):
    try:
        limit  = min(int(request.args.get("limit", 100)), 1000)
        after  = request.args.get("after", "0")
        search = request.args.get("search", "").strip()

        if search:
            # Discord search endpoint
            encoded = requests.utils.quote(search)
            members = bot_get(f"/guilds/{gid}/members/search?query={encoded}&limit=100") or []
        else:
            url = f"/guilds/{gid}/members?limit={limit}"
            if after and after != "0":
                url += f"&after={after}"
            members = bot_get(url) or []

        result = []
        for m in members:
            if m["user"].get("bot"):
                continue
            result.append({
                "id":        m["user"]["id"],
                "username":  m["user"]["username"],
                "avatar":    user_avatar_url(m["user"]),
                "joined_at": m.get("joined_at", ""),
                "roles":     m.get("roles", []),
                "nick":      m.get("nick"),
                "pending":   m.get("pending", False),
            })

        next_cursor = result[-1]["id"] if (not search and len(result) >= limit) else None
        return jsonify({"members": result, "next_cursor": next_cursor, "count": len(result)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/guild/<gid>/members/<uid>")
@require_login
def api_member_profile(gid, uid):
    try:
        m = bot_get(f"/guilds/{gid}/members/{uid}")
        if not m:
            return jsonify({"error": "Учасника не знайдено"}), 404
        return jsonify({
            "id":        m["user"]["id"],
            "username":  m["user"]["username"],
            "avatar":    user_avatar_url(m["user"]),
            "joined_at": m.get("joined_at", ""),
            "roles":     m.get("roles", []),
            "nick":      m.get("nick"),
            "bot":       m["user"].get("bot", False),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/guild/<gid>/members/<uid>/kick", methods=["POST"])
@require_login
def api_kick(gid, uid):
    b = request.get_json() or {}
    reason = b.get("reason", "Kicked via dashboard")
    try:
        r = requests.delete(f"{DISCORD_API}/guilds/{gid}/members/{uid}",
            headers={"Authorization": f"Bot {BOT_TOKEN}",
                     "X-Audit-Log-Reason": reason}, timeout=10)
        return jsonify({"ok": r.status_code in (200, 204)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/guild/<gid>/members/<uid>/ban", methods=["POST"])
@require_login
def api_ban(gid, uid):
    b = request.get_json() or {}
    reason = b.get("reason", "Banned via dashboard")
    try:
        r = requests.put(f"{DISCORD_API}/guilds/{gid}/bans/{uid}",
            headers={"Authorization": f"Bot {BOT_TOKEN}",
                     "Content-Type": "application/json",
                     "X-Audit-Log-Reason": reason},
            json={"delete_message_seconds": 86400}, timeout=10)
        return jsonify({"ok": r.status_code in (200, 204)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/guild/<gid>/members/<uid>/nickname", methods=["PATCH"])
@require_login
def api_nickname(gid, uid):
    b = request.get_json() or {}
    nick = b.get("nick", "")
    try:
        bot_patch(f"/guilds/{gid}/members/{uid}", {"nick": nick or None})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/guild/<gid>/members/<uid>/roles/<rid>", methods=["PUT"])
@require_login
def api_add_role(gid, uid, rid):
    try:
        bot_put(f"/guilds/{gid}/members/{uid}/roles/{rid}")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/guild/<gid>/members/<uid>/roles/<rid>", methods=["DELETE"])
@require_login
def api_remove_role(gid, uid, rid):
    try:
        bot_delete(f"/guilds/{gid}/members/{uid}/roles/{rid}")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────
#  API — BANS
# ─────────────────────────────────────────────
@app.route("/api/guild/<gid>/bans")
@require_login
def api_bans(gid):
    try:
        bans = bot_get(f"/guilds/{gid}/bans") or []
        return jsonify([{
            "user_id": b["user"]["id"],
            "username": b["user"]["username"],
            "discriminator": b["user"].get("discriminator", "0"),
            "avatar": user_avatar_url(b["user"]),
            "reason": b.get("reason") or "Без причини"
        } for b in bans])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/guild/<gid>/bans/<uid>", methods=["DELETE"])
@require_login
def api_unban(gid, uid):
    try:
        ok = bot_delete(f"/guilds/{gid}/bans/{uid}")
        return jsonify({"ok": ok})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────
#  API — MESSAGES
# ─────────────────────────────────────────────
@app.route("/api/guild/<gid>/send_message", methods=["POST"])
@require_login
def api_send_message(gid):
    b = request.get_json()
    channel_id  = b.get("channel_id")
    content     = b.get("content", "").strip()
    embed_title = b.get("embed_title", "").strip()
    embed_color = b.get("embed_color", "5865f2")
    embed_footer= b.get("embed_footer", "").strip()
    if not channel_id:
        return jsonify({"error": "Потрібен channel_id"}), 400
    try:
        payload = {}
        if content:
            payload["content"] = content
        if embed_title:
            emb = {
                "title": embed_title,
                "description": b.get("embed_desc", ""),
                "color": int(embed_color.lstrip("#"), 16),
            }
            if embed_footer:
                emb["footer"] = {"text": embed_footer}
            payload["embeds"] = [emb]
        if not payload:
            return jsonify({"error": "Потрібен текст або embed"}), 400
        msg = bot_post(f"/channels/{channel_id}/messages", payload)
        return jsonify({"ok": True, "message_id": msg.get("id")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/guild/<gid>/purge", methods=["POST"])
@require_login
def api_purge(gid):
    b = request.get_json()
    channel_id = b.get("channel_id")
    amount     = min(int(b.get("amount", 10)), 100)
    if not channel_id:
        return jsonify({"error": "Потрібен channel_id"}), 400
    try:
        msgs = bot_get(f"/channels/{channel_id}/messages?limit={amount}")
        if not msgs:
            return jsonify({"ok": True, "deleted": 0})
        ids = [m["id"] for m in msgs]
        if len(ids) == 1:
            bot_delete(f"/channels/{channel_id}/messages/{ids[0]}")
        else:
            bot_post(f"/channels/{channel_id}/messages/bulk-delete", {"messages": ids})
        return jsonify({"ok": True, "deleted": len(ids)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────
#  API — AUDIT LOG (з фільтром по типу дії)
# ─────────────────────────────────────────────
@app.route("/api/guild/<gid>/audit")
@require_login
def api_audit(gid):
    try:
        limit       = min(int(request.args.get("limit", 25)), 100)
        action_type = request.args.get("action_type")
        url = f"/guilds/{gid}/audit-logs?limit={limit}"
        if action_type:
            url += f"&action_type={action_type}"
        data = bot_get(url)
        if not data or "error" in data:
            return jsonify([])
        action_names = {
            1:"Оновлено сервер", 2:"Канал створено", 3:"Канал оновлено",
            4:"Канал видалено", 12:"Запрошення створено", 13:"Запрошення видалено",
            20:"Учасника кікнуто", 21:"Членів обрізано", 22:"Учасника забанено",
            23:"Учасника розбанено", 24:"Учасника оновлено", 25:"Ролі оновлено",
            26:"Роль додано", 27:"Роль видалено", 28:"Ролі видалено з учасника",
        }
        users_map = {u["id"]: u for u in data.get("users", [])}
        entries = []
        for e in data.get("audit_log_entries", []):
            uid = e.get("user_id")
            u   = users_map.get(uid, {})
            entries.append({
                "id":          e["id"],
                "action":      action_names.get(e["action_type"], f"Дія #{e['action_type']}"),
                "action_type": e["action_type"],
                "user":        u.get("username", "Невідомо"),
                "user_avatar": user_avatar_url(u) if u.get("id") else None,
                "reason":      e.get("reason") or "—",
                "target_id":   e.get("target_id"),
            })
        return jsonify(entries)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────
#  API — GUILD SETTINGS
# ─────────────────────────────────────────────
@app.route("/api/guild/<gid>/settings", methods=["PATCH"])
@require_login
def api_guild_settings(gid):
    b = request.get_json()
    payload = {}
    if "name" in b and b["name"].strip():
        payload["name"] = b["name"].strip()
    if "description" in b:
        payload["description"] = b["description"]
    if not payload:
        return jsonify({"error": "Нічого для оновлення"}), 400
    try:
        g = bot_patch(f"/guilds/{gid}", payload)
        return jsonify({"ok": True, "name": g.get("name")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 http://localhost:8080")
    app.run(debug=False, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
