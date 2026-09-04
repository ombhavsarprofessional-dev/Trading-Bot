# Deployment Guide: Cloudflare Pages (Frontend) + Python Backend

This guide details how to deploy the **NSE Swing Trading Bot** using Cloudflare Pages for the frontend and running the lightweight Python backend on a VPS, local home server, or cloud VM.

---

## 1. Architecture Overview

- **Frontend**: Static SPA (`HTML`, `CSS`, `JS`) hosted globally on **Cloudflare Pages** (Free, lightning fast edge CDN).
- **Backend**: Python 3.10+ Flask API with APScheduler and SQLite running on a VPS or home server.
- **Connection Options**:
  - **Option A (Recommended)**: Cloudflare Tunnel (`cloudflared`) to securely expose your backend without opening router ports or paying for static IPs.
  - **Option B**: Direct VPS IP/domain with Nginx and SSL.
  - **Option C**: Cloudflare Worker reverse-proxy (`deployment/cloudflare_worker.js`).

---

## 2. Deploying the Frontend to Cloudflare Pages

### Method 1: Via GitHub Integration (Automated CI/CD)
1. Push this repository to GitHub.
2. In your [Cloudflare Dashboard](https://dash.cloudflare.com/), navigate to **Workers & Pages** &gt; **Create application** &gt; **Pages** &gt; **Connect to Git**.
3. Select your repository.
4. In Build Settings:
   - **Framework preset**: None
   - **Build command**: *(Leave blank)*
   - **Build output directory**: `frontend`
5. Click **Save and Deploy**. Cloudflare will deploy the site and provide a `*.pages.dev` URL.

### Method 2: Direct Upload via Wrangler CLI
If you prefer not using Git:
```bash
npm install -g wrangler
wrangler pages deploy frontend --project-name=nse-swing-bot
```

### Configuring API Base URL
In `frontend/js/app.js`, the app automatically uses the same domain if served together. If your backend is hosted on a separate domain (e.g., `https://api.yourdomain.com`), you can set it in `frontend/index.html` right before `app.js`:
```html
<script>
  window.APP_CONFIG = {
    API_BASE_URL: "https://api.yourdomain.com"
  };
</script>
<script src="js/app.js"></script>
```

---

## 3. Running the Python Backend (VPS or Server)

### Prerequisites
Install Python 3.10+ and git:
```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git
```

### Setup & Run
```bash
git clone <your-repo-url> "Trading Bot"
cd "Trading Bot"

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Run the server
python run_server.py
```

### Running as a Persistent Systemd Service (Linux)
Create `/etc/systemd/system/nse-bot.service`:
```ini
[Unit]
Description=NSE Swing Trading Bot API & Scheduler
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/Trading Bot
ExecStart=/home/ubuntu/Trading Bot/venv/bin/python run_server.py
Restart=always
RestartSec=10
Environment="BOT_USERNAME=admin"
Environment="BOT_PASSWORD=your_secure_password"
Environment="JWT_SECRET_KEY=your_secret_key"
Environment="BROKER_MODE=MOCK"

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable nse-bot
sudo systemctl start nse-bot
sudo systemctl status nse-bot
```

---

## 4. Secure Connection with Cloudflare Tunnel (Zero Port Forwarding)

You can expose the local Flask backend (`http://127.0.0.1:5000`) securely to the internet without opening firewall ports:

1. Install `cloudflared`:
   ```bash
   curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i cloudflared.deb
   ```
2. Login and create a tunnel:
   ```bash
   cloudflared tunnel login
   cloudflared tunnel create nse-backend
   ```
3. Route your custom domain/subdomain:
   ```bash
   cloudflared tunnel route dns nse-backend api.yourdomain.com
   ```
4. Run tunnel:
   ```bash
   cloudflared tunnel run --url http://127.0.0.1:5000 nse-backend
   ```
Now your backend API is accessible over HTTPS with enterprise-grade Cloudflare DDoS protection.
