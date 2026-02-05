# EC2 Ubuntu Deployment Guide

## Prerequisites

### 1. EC2 Instance Setup
- **AMI**: Ubuntu 22.04 LTS (ami-0c55b159cbfafe1f0 or latest)
- **Instance Type**: 
  - Development: `t3.medium` (2 vCPU, 4GB RAM)
  - Production: `t3.large` (2 vCPU, 8GB RAM) or `g4dn.xlarge` for GPU
- **Storage**: 50GB EBS (gp3)
- **Security Group**: Allow ports 22 (SSH), 80 (HTTP), 443 (HTTPS)

### 2. SSH Setup
```bash
# Download your EC2 key pair (e.g., my-key.pem)
chmod 400 my-key.pem
ssh -i my-key.pem ubuntu@<your-ec2-public-ip>
```

---

## Step 1: Initial Server Setup

```bash
# Update system packages
sudo apt update
sudo apt upgrade -y

# Install Python and essential tools
sudo apt install -y python3.11 python3.11-venv python3-pip git curl wget
sudo apt install -y build-essential libssl-dev libffi-dev python3-dev

# Install system dependencies for audio processing
sudo apt install -y ffmpeg libsndfile1 libsndfile1-dev

# Create application directory
sudo mkdir -p /opt/scam-honeypot
sudo chown ubuntu:ubuntu /opt/scam-honeypot
cd /opt/scam-honeypot
```

---

## Step 2: Clone Repository and Setup

```bash
# Clone your repository (replace with your repo URL)
git clone https://github.com/your-username/buildathon-ai-impact.git .

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt

# Install additional production dependencies
pip install gunicorn python-multipart
```

---

## Step 3: Environment Configuration

```bash
# Copy environment file
cp backend/.env.example backend/.env

# Edit .env for production
nano backend/.env
```

**Update these values in `.env`:**

```env
# Set production device
DEVICE=cpu  # or cuda for GPU instances

# Increase workers for production (CPU cores - 1)
API_WORKERS=3  # For t3.large with 2 vCPU, use 1-2

# Set specific CORS origins
CORS_ORIGINS=["https://your-domain.com"]  # Replace with your domain

# Change API key for production
API_SECRET_KEY=your-secure-api-key-here  # Generate a strong key

# Set log level
LOG_LEVEL=INFO

# Demo mode off for production
DEMO_MODE=false

# LLM API settings (if using external API)
LLM_USE_API=true
LLM_API_BASE_URL=http://localhost:8001/v1  # If using Ollama locally
```

---

## Step 4: Download Models

```bash
cd /opt/scam-honeypot/backend

# Download all required models (this may take 10-30 minutes depending on internet speed)
python scripts/download_models.py

# You should see output like:
# ✓ whisper model validated
# ✓ distilbert model validated
# ✓ spacy model validated
# ✓ tts model validated
# ✓ voice_detector model validated
# ✓ llm model validated
```

---

## Step 5: Create Systemd Service

Create `/opt/scam-honeypot/scam-honeypot.service`:

```bash
sudo nano /etc/systemd/system/scam-honeypot.service
```

Add the following content:

```ini
[Unit]
Description=Scam Honeypot AI Backend Service
After=network.target

[Service]
Type=notify
User=ubuntu
WorkingDirectory=/opt/scam-honeypot
Environment="PATH=/opt/scam-honeypot/venv/bin"
Environment="PYTHONUNBUFFERED=1"

# Start the application with Gunicorn
ExecStart=/opt/scam-honeypot/venv/bin/gunicorn \
    --workers 3 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 127.0.0.1:8000 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    app.main:app

# Restart on failure
Restart=on-failure
RestartSec=10

# Process management
KillMode=mixed
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable scam-honeypot
sudo systemctl start scam-honeypot

# Check status
sudo systemctl status scam-honeypot
```

---

## Step 6: Setup Nginx Reverse Proxy

```bash
# Install Nginx
sudo apt install -y nginx

# Create Nginx configuration
sudo nano /etc/nginx/sites-available/scam-honeypot
```

Add the following:

```nginx
upstream scam_honeypot {
    server 127.0.0.1:8000;
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS configuration
server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # SSL certificates (use Let's Encrypt or AWS ACM)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    # Proxy settings
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

    # Enable gzip compression
    gzip on;
    gzip_types text/plain text/css text/xml text/javascript application/x-javascript application/xml+rss;
    gzip_vary on;
    gzip_min_length 1000;
}
```

Enable the site:

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/scam-honeypot /etc/nginx/sites-enabled/

# Remove default site
sudo rm /etc/nginx/sites-enabled/default

# Test Nginx configuration
sudo nginx -t

# Start Nginx
sudo systemctl restart nginx
```

---

## Step 7: SSL Certificate (Let's Encrypt)

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot certonly --nginx -d your-domain.com -d www.your-domain.com

# Auto-renewal setup (already enabled by default on Ubuntu 22.04)
sudo systemctl enable certbot.timer
```

---

## Step 8: Monitoring and Logs

```bash
# View service logs
sudo journalctl -u scam-honeypot -f

# View Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# View application logs
tail -f /opt/scam-honeypot/backend/logs/app.log
```

---

## Step 9: Health Check

```bash
# Test locally
curl http://127.0.0.1:8000/health

# Test via domain
curl https://your-domain.com/health

# Response should be:
# {"status":"success","message":"Service is healthy","timestamp":"2026-02-05T..."}
```

---

## Step 10: Backup Strategy

```bash
# Create backup script
sudo nano /usr/local/bin/backup-scam-honeypot.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/backups/scam-honeypot"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup models (optional - large)
tar -czf $BACKUP_DIR/models_$DATE.tar.gz /opt/scam-honeypot/backend/models/

# Backup .env
cp /opt/scam-honeypot/backend/.env $BACKUP_DIR/.env_$DATE

# Keep only last 7 days of backups
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete
find $BACKUP_DIR -name ".env_*" -mtime +7 -delete

echo "Backup completed: $BACKUP_DIR"
```

```bash
# Make executable
sudo chmod +x /usr/local/bin/backup-scam-honeypot.sh

# Add to crontab for daily backups at 2 AM
sudo crontab -e
# Add line: 0 2 * * * /usr/local/bin/backup-scam-honeypot.sh
```

---

## Deployment Commands Summary

```bash
# Quick deployment checklist
sudo systemctl status scam-honeypot       # Check service status
sudo systemctl restart scam-honeypot      # Restart service
sudo systemctl stop scam-honeypot         # Stop service
sudo systemctl start scam-honeypot        # Start service

# View logs
sudo journalctl -u scam-honeypot -n 50    # Last 50 lines
sudo journalctl -u scam-honeypot -f       # Follow logs

# Update application
cd /opt/scam-honeypot
git pull origin main
source venv/bin/activate
pip install -r backend/requirements.txt
sudo systemctl restart scam-honeypot
```

---

## Troubleshooting

### Service won't start
```bash
sudo journalctl -u scam-honeypot -n 100
# Check for missing dependencies or file permissions
```

### Permission denied errors
```bash
sudo chown -R ubuntu:ubuntu /opt/scam-honeypot
sudo chmod -R 755 /opt/scam-honeypot
```

### Port 8000 already in use
```bash
sudo lsof -i :8000
# Kill the process if needed
sudo kill -9 <PID>
```

### Models not loading
```bash
cd /opt/scam-honeypot/backend
source ../venv/bin/activate
python scripts/download_models.py
```

### Nginx issues
```bash
sudo nginx -t              # Test configuration
sudo systemctl restart nginx
sudo journalctl -u nginx -f
```

---

## Performance Optimization

### For CPU-only instances:
- Use `WHISPER_MODEL_NAME=tiny` or `base`
- Set `API_WORKERS=1` or `2`
- Enable `LLM_USE_API=true` to offload LLM

### For GPU instances:
- Set `DEVICE=cuda`
- Use larger models (`WHISPER_MODEL_NAME=large`)
- Set `API_WORKERS=4`

### Database connection pooling (if using database):
```python
# Add to requirements.txt
psycopg2-binary==2.9.9
sqlalchemy==2.0.0
```

---

## Security Checklist

- [ ] Change `API_SECRET_KEY` to a strong value
- [ ] Restrict CORS origins to your domain
- [ ] Enable SSL/TLS certificates
- [ ] Configure security groups to limit access
- [ ] Set up VPC with private subnets
- [ ] Enable CloudWatch monitoring
- [ ] Set up automated backups
- [ ] Configure log rotation
- [ ] Disable password SSH (use key pairs only)
- [ ] Set up DDoS protection (AWS Shield)

---

## Cost Optimization

- Use `t3.medium` for development/testing
- Use `t3.large` for production with 1-2 workers
- Consider `t3a.medium` for cost savings
- Use `g4dn.xlarge` only if GPU acceleration is needed
- Enable EBS auto-scaling for storage
- Use spot instances for non-critical workloads
- Monitor CloudWatch for optimization opportunities

---

## Next Steps

1. Update `your-domain.com` in all configurations
2. Generate a strong API key: `openssl rand -hex 32`
3. Set up CI/CD pipeline (GitHub Actions, GitLab CI)
4. Configure monitoring (CloudWatch, Datadog)
5. Set up alerting for failures
6. Create scaling policies for auto-scaling groups
