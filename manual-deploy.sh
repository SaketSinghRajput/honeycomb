#!/bin/bash
# manual-deploy.sh - Step-by-step manual deployment guide

# This script provides interactive prompts for EC2 deployment

echo "======================================"
echo "Scam Honeypot - EC2 Deployment Helper"
echo "======================================"
echo ""

# Prompt for configuration
read -p "Enter your domain name (or 'localhost' for testing): " DOMAIN
read -p "Enter EC2 instance IP or hostname: " EC2_HOST
read -p "Enter path to SSH key file (default: ~/.ssh/id_rsa): " SSH_KEY_PATH
SSH_KEY_PATH=${SSH_KEY_PATH:-~/.ssh/id_rsa}

echo ""
echo "Configuration Summary:"
echo "  Domain: $DOMAIN"
echo "  EC2 Host: $EC2_HOST"
echo "  SSH Key: $SSH_KEY_PATH"
echo ""

# Function to run command on EC2
run_on_ec2() {
    echo "$ $1"
    ssh -i "$SSH_KEY_PATH" ubuntu@"$EC2_HOST" "$1"
}

# Menu
while true; do
    echo ""
    echo "Choose deployment step:"
    echo "1. Connect to EC2 (test SSH)"
    echo "2. Update system and install dependencies"
    echo "3. Clone repository and setup Python environment"
    echo "4. Download models"
    echo "5. Setup systemd service"
    echo "6. Setup Nginx and SSL"
    echo "7. Start and verify service"
    echo "8. Full automated deployment (1-7)"
    echo "9. View service logs"
    echo "10. Check service status"
    echo "11. Exit"
    echo ""
    read -p "Enter choice (1-11): " CHOICE

    case $CHOICE in
        1)
            echo "Connecting to EC2..."
            ssh -i "$SSH_KEY_PATH" ubuntu@"$EC2_HOST"
            ;;
        2)
            echo "Step 1: Installing dependencies..."
            run_on_ec2 "
            sudo apt update && \
            sudo apt upgrade -y && \
            sudo apt install -y python3.11 python3.11-venv python3-pip git curl wget && \
            sudo apt install -y build-essential libssl-dev libffi-dev python3-dev && \
            sudo apt install -y ffmpeg libsndfile1 libsndfile1-dev && \
            sudo apt install -y nginx certbot python3-certbot-nginx && \
            echo 'Dependencies installed successfully!'
            "
            ;;
        3)
            echo "Step 2: Setting up repository and Python environment..."
            run_on_ec2 "
            sudo mkdir -p /opt/scam-honeypot && \
            sudo chown ubuntu:ubuntu /opt/scam-honeypot && \
            cd /opt/scam-honeypot && \
            git clone https://github.com/your-username/buildathon-ai-impact.git . && \
            python3.11 -m venv venv && \
            source venv/bin/activate && \
            pip install --upgrade pip && \
            pip install -r backend/requirements.txt && \
            pip install gunicorn python-multipart && \
            echo 'Python environment ready!'
            "
            ;;
        4)
            echo "Step 3: Downloading models (this may take 10-30 minutes)..."
            run_on_ec2 "
            cd /opt/scam-honeypot/backend && \
            source ../venv/bin/activate && \
            python scripts/download_models.py
            "
            ;;
        5)
            echo "Step 4: Setting up systemd service..."
            run_on_ec2 "
            sudo tee /etc/systemd/system/scam-honeypot.service > /dev/null <<'SERVICE'
[Unit]
Description=Scam Honeypot AI Backend Service
After=network.target

[Service]
Type=notify
User=ubuntu
WorkingDirectory=/opt/scam-honeypot
Environment=\"PATH=/opt/scam-honeypot/venv/bin\"
Environment=\"PYTHONUNBUFFERED=1\"

ExecStart=/opt/scam-honeypot/venv/bin/gunicorn \\
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
SERVICE
            sudo systemctl daemon-reload && \
            sudo systemctl enable scam-honeypot && \
            echo 'Systemd service created and enabled!'
            "
            ;;
        6)
            echo "Step 5: Setting up Nginx..."
            read -p "Enter domain for SSL (or press Enter for testing without SSL): " SSL_DOMAIN
            
            if [ -z "$SSL_DOMAIN" ]; then
                echo "Setting up Nginx without SSL..."
                run_on_ec2 "
                sudo tee /etc/nginx/sites-available/scam-honeypot > /dev/null <<'NGINX'
upstream scam_honeypot {
    server 127.0.0.1:8000;
}

server {
    listen 80 default_server;
    server_name _;

    location / {
        proxy_pass http://scam_honeypot;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \"upgrade\";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINX
                sudo ln -sf /etc/nginx/sites-available/scam-honeypot /etc/nginx/sites-enabled/ && \
                sudo rm -f /etc/nginx/sites-enabled/default && \
                sudo nginx -t && \
                sudo systemctl restart nginx && \
                echo 'Nginx configured (HTTP only)!'
                "
            else
                echo "Setting up Nginx with SSL for $SSL_DOMAIN..."
                run_on_ec2 "
                sudo tee /etc/nginx/sites-available/scam-honeypot > /dev/null <<'NGINX'
upstream scam_honeypot {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name $SSL_DOMAIN www.$SSL_DOMAIN;
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name $SSL_DOMAIN www.$SSL_DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$SSL_DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$SSL_DOMAIN/privkey.pem;

    add_header Strict-Transport-Security \"max-age=31536000; includeSubDomains\" always;
    add_header X-Content-Type-Options \"nosniff\" always;
    add_header X-Frame-Options \"DENY\" always;

    location / {
        proxy_pass http://scam_honeypot;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \"upgrade\";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINX
                sudo ln -sf /etc/nginx/sites-available/scam-honeypot /etc/nginx/sites-enabled/ && \
                sudo rm -f /etc/nginx/sites-enabled/default && \
                sudo nginx -t && \
                sudo systemctl restart nginx && \
                echo 'Getting SSL certificate...' && \
                sudo certbot certonly --nginx -d $SSL_DOMAIN -d www.$SSL_DOMAIN && \
                sudo systemctl restart nginx && \
                echo 'Nginx configured with SSL!'
                "
            fi
            ;;
        7)
            echo "Step 6: Starting service and verifying..."
            run_on_ec2 "
            sudo systemctl start scam-honeypot && \
            sleep 2 && \
            sudo systemctl status scam-honeypot && \
            echo '' && \
            echo 'Testing health endpoint...' && \
            curl http://127.0.0.1:8000/health || echo 'Health check failed - service may still be starting'
            "
            ;;
        8)
            echo "Running full automated deployment (steps 1-7)..."
            echo "This will take 15-30 minutes depending on model download speed."
            read -p "Continue? (y/n): " CONFIRM
            if [ "$CONFIRM" = "y" ]; then
                # Run all steps
                echo "Installing dependencies..."
                run_on_ec2 "sudo apt update && sudo apt upgrade -y && sudo apt install -y python3.11 python3.11-venv python3-pip git curl wget build-essential libssl-dev libffi-dev python3-dev ffmpeg libsndfile1 libsndfile1-dev nginx certbot python3-certbot-nginx"
                
                echo "Setting up repository..."
                run_on_ec2 "sudo mkdir -p /opt/scam-honeypot && sudo chown ubuntu:ubuntu /opt/scam-honeypot && cd /opt/scam-honeypot && git clone https://github.com/your-username/buildathon-ai-impact.git . 2>/dev/null || git pull"
                
                echo "Setting up Python environment..."
                run_on_ec2 "cd /opt/scam-honeypot && python3.11 -m venv venv && source venv/bin/activate && pip install --upgrade pip && pip install -r backend/requirements.txt && pip install gunicorn python-multipart"
                
                echo "Downloading models..."
                run_on_ec2 "cd /opt/scam-honeypot/backend && source ../venv/bin/activate && python scripts/download_models.py"
                
                echo "Creating systemd service and Nginx config..."
                run_on_ec2 "sudo systemctl enable scam-honeypot && sudo systemctl start scam-honeypot"
                
                echo "Deployment complete!"
            fi
            ;;
        9)
            echo "Service logs (last 50 lines):"
            run_on_ec2 "sudo journalctl -u scam-honeypot -n 50"
            ;;
        10)
            echo "Service status:"
            run_on_ec2 "sudo systemctl status scam-honeypot"
            ;;
        11)
            echo "Exiting..."
            exit 0
            ;;
        *)
            echo "Invalid choice. Please try again."
            ;;
    esac
done
