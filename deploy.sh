#!/bin/bash
# deploy.sh - One-click deployment script for EC2 Ubuntu

set -e  # Exit on error

echo "========================================"
echo "Scam Honeypot AI - EC2 Deployment Script"
echo "========================================"

# Configuration
APP_DIR="/opt/scam-honeypot"
APP_USER="ubuntu"
DOMAIN=${1:-"localhost"}
API_KEY=${2:-"$(openssl rand -hex 32)"}

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_info() {
    echo -e "${YELLOW}[i]${NC} $1"
}

# Step 1: System updates
print_info "Step 1: Updating system packages..."
sudo apt update
sudo apt upgrade -y
print_status "System updated"

# Step 2: Install dependencies
print_info "Step 2: Installing dependencies..."
sudo apt install -y python3 python3-venv python3-pip git curl wget
sudo apt install -y build-essential libssl-dev libffi-dev python3-dev
sudo apt install -y ffmpeg libsndfile1 libsndfile1-dev
sudo apt install -y nginx certbot python3-certbot-nginx
print_status "Dependencies installed"

# Step 3: Create application directory
print_info "Step 3: Setting up application directory..."
sudo mkdir -p $APP_DIR
sudo chown $APP_USER:$APP_USER $APP_DIR
print_status "Application directory ready"

# Step 4: Clone repository
print_info "Step 4: Cloning repository..."
if [ -d "$APP_DIR/.git" ]; then
    cd $APP_DIR
    git pull origin main
else
    print_error "Repository not found. Manual clone required:"
    print_info "git clone <your-repo-url> $APP_DIR"
    exit 1
fi
print_status "Repository cloned/updated"

# Step 5: Setup Python environment
print_info "Step 5: Setting up Python virtual environment..."
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
pip install gunicorn python-multipart
print_status "Python environment ready"

# Step 6: Configure environment
print_info "Step 6: Configuring environment..."
if [ ! -f "$APP_DIR/backend/.env" ]; then
    cp backend/.env.example backend/.env
    
    # Update .env values
    sed -i "s/API_SECRET_KEY=.*/API_SECRET_KEY=$API_KEY/" backend/.env
    sed -i 's/DEVICE=auto/DEVICE=cpu/' backend/.env
    sed -i 's/DEMO_MODE=false/DEMO_MODE=false/' backend/.env
    
    print_info "Generated API_SECRET_KEY: $API_KEY"
    print_info "Save this key securely!"
fi
print_status ".env configured"

# Step 7: Download models
print_info "Step 7: Downloading models to $APP_DIR/backend/models (this may take 10-30 minutes)..."
cd $APP_DIR/backend

# Ensure models directory exists and set environment variable
export MODELS_DIR="$APP_DIR/backend/models"
mkdir -p "$MODELS_DIR"

# Run model download script
python scripts/download_models.py

if [ $? -eq 0 ]; then
    print_status "Models downloaded successfully to $MODELS_DIR"
else
    print_error "Model download failed"
    exit 1
fi

# Step 8: Create systemd service
print_info "Step 8: Creating systemd service..."
sudo tee /etc/systemd/system/scam-honeypot.service > /dev/null <<EOF
[Unit]
Description=Scam Honeypot AI Backend Service
After=network.target

[Service]
Type=notify
User=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
Environment="PYTHONUNBUFFERED=1"

ExecStart=$APP_DIR/venv/bin/gunicorn \\
    --workers 2 \\
    --worker-class uvicorn.workers.UvicornWorker \\
    --bind 127.0.0.1:8000 \\
    --access-logfile - \\
    --error-logfile - \\
    --log-level info \\
    app.main:app

Restart=on-failure
RestartSec=10
KillMode=mixed
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable scam-honeypot
print_status "Systemd service created"

# Step 9: Configure Nginx
print_info "Step 9: Configuring Nginx..."
sudo tee /etc/nginx/sites-available/scam-honeypot > /dev/null <<'EOF'
upstream scam_honeypot {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2 default_server;
    server_name _;

    # SSL - Update with your certificate paths
    # ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    location / {
        proxy_pass http://scam_honeypot;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    gzip on;
    gzip_types text/plain text/css text/xml text/javascript application/x-javascript application/xml+rss;
}
EOF

sudo ln -sf /etc/nginx/sites-available/scam-honeypot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
print_status "Nginx configured"

# Step 10: Start service
print_info "Step 10: Starting application service..."
sudo systemctl start scam-honeypot
sleep 2
sudo systemctl status scam-honeypot
print_status "Application started"

# Summary
echo ""
echo "========================================"
echo -e "${GREEN}Deployment Completed!${NC}"
echo "========================================"
echo ""
print_info "Application running at: http://localhost:8000"
print_info "API Key: $API_KEY"
print_info ""
print_info "Next steps:"
echo "  1. Update Nginx SSL certificates (uncomment in /etc/nginx/sites-available/scam-honeypot)"
echo "  2. Set up Let's Encrypt: sudo certbot certonly --nginx -d your-domain.com"
echo "  3. Update API_SECRET_KEY in backend/.env to: $API_KEY"
echo "  4. Verify service: sudo systemctl status scam-honeypot"
echo "  5. View logs: sudo journalctl -u scam-honeypot -f"
echo ""
print_info "API Documentation:"
echo "  - Health Check: GET /health"
echo "  - Detect: POST /api/v1/detect"
echo "  - Extract: POST /api/v1/extract"
echo "  - Engage: POST /api/v1/engage"
echo "  - Full Pipeline: POST /api/v1/full-pipeline"
echo ""
