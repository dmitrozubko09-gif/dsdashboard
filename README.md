# ⚡ RAVEN PANEL — Discord Bot Dashboard

## Деплой на Railway (рекомендовано)

### 1. GitHub
```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/YOUR_USERNAME/raven-panel.git
git push -u origin main
```

### 2. Railway
1. Зайди на [railway.app](https://railway.app)
2. New Project → Deploy from GitHub → вибери репо
3. Додай змінні середовища:

| Змінна | Значення |
|--------|----------|
| `DISCORD_CLIENT_ID` | твій Client ID |
| `DISCORD_CLIENT_SECRET` | твій Client Secret |
| `DISCORD_BOT_TOKEN` | токен бота |
| `REDIRECT_URI` | `https://YOUR-APP.railway.app/callback` |
| `SECRET_KEY` | будь-який довгий рядок |

### 3. Discord Developer Portal
- Зайди в OAuth2 → Redirects
- Додай: `https://YOUR-APP.railway.app/callback`

## Локальний запуск
```bash
pip install -r requirements.txt
python app.py
```
