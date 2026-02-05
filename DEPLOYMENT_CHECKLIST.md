# EC2 Deployment Checklist & Runbook

## Pre-Deployment (1-2 hours)

### AWS Account Setup
- [ ] AWS account created and verified
- [ ] Billing alerts configured
- [ ] IAM user created with EC2/S3/CloudWatch permissions
- [ ] MFA enabled on root account
- [ ] Budget set to ~$150/month

### Local Preparation
- [ ] Repository cloned locally
- [ ] All code tested locally (`python -m pytest` if tests exist)
- [ ] `.env.example` reviewed and updated
- [ ] `requirements.txt` verified
- [ ] `deploy.sh` script reviewed

### Domain Setup (Optional)
- [ ] Domain registered (Route 53 or external registrar)
- [ ] DNS records ready to update
- [ ] SSL certificate plan decided (Let's Encrypt or AWS ACM)

---

## Deployment Phase (15-30 minutes active, 30+ minutes waiting)

### Step 1: AWS Infrastructure (5 minutes)

```bash
# 1. Create security group
aws ec2 create-security-group --group-name scam-honeypot-sg \
  --description "Scam Honeypot API" --region us-east-1

# 2. Allow SSH/HTTP/HTTPS
SG_ID="sg-xxx"
aws ec2 authorize-security-group-ingress --group-id $SG_ID \
  --protocol tcp --port 22 --cidr YOUR_IP/32
aws ec2 authorize-security-group-ingress --group-id $SG_ID \
  --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $SG_ID \
  --protocol tcp --port 443 --cidr 0.0.0.0/0

# 3. Create key pair
aws ec2 create-key-pair --key-name scam-honeypot-key --region us-east-1 \
  > scam-honeypot-key.pem
chmod 400 scam-honeypot-key.pem

# Save EC2_IP from launch output
EC2_IP="18.234.56.78"
```

### Step 2: Launch EC2 Instance (5 minutes)

```bash
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.large \
  --key-name scam-honeypot-key \
  --security-group-ids sg-xxx \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=50,VolumeType=gp3}' \
  --region us-east-1

# Wait for instance to be running (1-2 minutes)
INSTANCE_ID="i-xxx"

# Get public IP
aws ec2 describe-instances --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].PublicIpAddress'
```

### Step 3: Connect and Deploy (5 minutes active)

```bash
# 1. SSH into instance (wait 30-60 seconds after launch)
ssh -i scam-honeypot-key.pem ubuntu@$EC2_IP

# 2. Update system
sudo apt update
sudo apt upgrade -y

# 3. Install dependencies
sudo apt install -y python3.11 python3.11-venv python3-pip git
sudo apt install -y build-essential libssl-dev libffi-dev python3-dev
sudo apt install -y ffmpeg libsndfile1 libsndfile1-dev
sudo apt install -y nginx certbot python3-certbot-nginx

# 4. Clone repository
git clone https://github.com/your-username/buildathon-ai-impact.git /opt/scam-honeypot
cd /opt/scam-honeypot

# 5. Setup Python environment
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
pip install gunicorn
```

### Step 4: Download Models (15-30 minutes waiting)

```bash
cd backend
python scripts/download_models.py
# ✓ whisper model validated
# ✓ distilbert model validated
# ✓ spacy model validated
# ✓ tts model validated
# ✓ voice_detector model validated
# ✓ llm model validated
```

### Step 5: Configure and Deploy (5 minutes)

```bash
# 1. Setup environment
cp .env.example .env
nano .env
# Update: API_SECRET_KEY, DEVICE=cpu, CORS_ORIGINS

# 2. Create systemd service
sudo nano /etc/systemd/system/scam-honeypot.service
# Paste content from DEPLOYMENT_GUIDE.md

sudo systemctl daemon-reload
sudo systemctl enable scam-honeypot
sudo systemctl start scam-honeypot

# 3. Configure Nginx
sudo nano /etc/nginx/sites-available/scam-honeypot
# Paste content from DEPLOYMENT_GUIDE.md

sudo ln -sf /etc/nginx/sites-available/scam-honeypot /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

### Step 6: Setup SSL (Optional, 5 minutes)

```bash
# If using Let's Encrypt
sudo certbot certonly --nginx -d your-domain.com -d www.your-domain.com

# Update Nginx config with certificate paths
sudo nano /etc/nginx/sites-available/scam-honeypot
# Uncomment SSL lines and restart
sudo systemctl restart nginx
```

### Step 7: Verification (2 minutes)

```bash
# Check service
sudo systemctl status scam-honeypot

# View logs
sudo journalctl -u scam-honeypot -n 20

# Test API
curl http://localhost:8000/health
curl https://your-domain.com/health

# Expected response:
# {"status":"success","message":"Service is healthy","timestamp":"..."}
```

---

## Post-Deployment (30 minutes)

### Monitoring Setup

```bash
# CloudWatch agent installation
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i amazon-cloudwatch-agent.deb

# Create config (see AWS_EC2_DEPLOYMENT.md)
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 -s -c file:config.json
```

### Testing

```bash
# 1. Health check
curl https://your-domain.com/health

# 2. Scam detection
curl -X POST https://your-domain.com/api/v1/detect \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_API_KEY" \
  -d '{"transcript":"Send OTP now!"}'

# 3. Entity extraction
curl -X POST https://your-domain.com/api/v1/extract \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_API_KEY" \
  -d '{"transcript":"UPI: scam@paytm, +919876543210"}'
```

### DNS Configuration (if using custom domain)

```bash
# Update Route 53
aws route53 change-resource-record-sets \
  --hosted-zone-id Z123456 \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "api.your-domain.com",
        "Type": "A",
        "TTL": 300,
        "ResourceRecords": [{"Value": "'$EC2_IP'"}]
      }
    }]
  }'

# Verify DNS (wait 1-2 minutes)
nslookup api.your-domain.com
```

### Documentation

- [ ] Save EC2 instance ID and IP
- [ ] Save API key securely (password manager)
- [ ] Document any custom configurations
- [ ] Create runbook for team members

---

## First Day Checks

### Morning (Day 1)
- [ ] Service still running: `sudo systemctl status scam-honeypot`
- [ ] No errors in logs: `sudo journalctl -u scam-honeypot`
- [ ] Disk space available: `df -h`
- [ ] Memory not maxed: `free -h`

### Afternoon (Day 1)
- [ ] Check CloudWatch metrics
- [ ] Test API endpoints again
- [ ] Verify DNS/SSL working
- [ ] Review and test scaling (optional)

### End of Week
- [ ] All metrics normal
- [ ] No unexpected errors
- [ ] Backup configured and tested
- [ ] Team familiar with access and operations

---

## Common Issues & Fixes

### Issue: "Service failed to start"
```bash
sudo journalctl -u scam-honeypot -n 100
# Check for missing models, wrong paths, permission errors
```

### Issue: "Port 8000 already in use"
```bash
sudo lsof -i :8000
sudo kill -9 <PID>
sudo systemctl start scam-honeypot
```

### Issue: "Certificate validation failed"
```bash
# Update Nginx config with correct paths
sudo nano /etc/nginx/sites-available/scam-honeypot
sudo nginx -t
sudo systemctl reload nginx
```

### Issue: "Out of memory"
```bash
# Reduce workers
sudo nano /etc/systemd/system/scam-honeypot.service
# Change --workers 3 to --workers 2
sudo systemctl daemon-reload
sudo systemctl restart scam-honeypot
```

### Issue: "Models not loading"
```bash
cd /opt/scam-honeypot/backend
source ../venv/bin/activate
python scripts/download_models.py
sudo systemctl restart scam-honeypot
```

---

## Maintenance Schedule

### Daily
- Monitor via CloudWatch
- Quick health check: `curl https://your-domain.com/health`

### Weekly
```bash
# Check logs for errors
sudo journalctl -u scam-honeypot -S "-7 days" | grep ERROR

# Review resource usage
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value=$INSTANCE_ID \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-08T00:00:00Z \
  --period 3600 \
  --statistics Average,Maximum
```

### Monthly
```bash
# Update system
sudo apt update && sudo apt upgrade

# Verify backups working
# Check CloudWatch logs retention

# Review costs
# aws ce get-cost-and-usage ...

# Backup configuration
tar -czf backup_$(date +%Y%m%d).tar.gz \
  /opt/scam-honeypot/backend/.env \
  /opt/scam-honeypot/backend/logs
```

### Quarterly
- Security audit of configuration
- Performance optimization review
- Disaster recovery drill
- Update dependencies

---

## Quick Access Reference

```bash
# Save these in ~/.bashrc or create alias file

# SSH Access
alias ssh-honeypot='ssh -i /path/to/scam-honeypot-key.pem ubuntu@$EC2_IP'

# Service Control
alias hp-status='sudo systemctl status scam-honeypot'
alias hp-start='sudo systemctl start scam-honeypot'
alias hp-stop='sudo systemctl stop scam-honeypot'
alias hp-restart='sudo systemctl restart scam-honeypot'
alias hp-logs='sudo journalctl -u scam-honeypot -f'

# Directory Navigation
alias hp='cd /opt/scam-honeypot'
alias hpenv='nano /opt/scam-honeypot/backend/.env'

# Health Checks
alias hp-health='curl https://your-domain.com/health | jq'
```

---

## Emergency Contacts & Escalation

### Critical Issues
1. **Service Down**: Restart → Check logs → Rollback if needed
2. **High CPU/Memory**: Reduce workers → Restart → Scale up instance
3. **Disk Full**: Clean logs → Check disk usage → Expand EBS if needed
4. **SSL Certificate Expired**: Renew: `sudo certbot renew`

### Support Resources
- AWS Support: https://console.aws.amazon.com/support/
- Application Logs: `sudo journalctl -u scam-honeypot`
- Nginx Logs: `/var/log/nginx/`
- GitHub Issues: Your repository

---

## Success Metrics

After deployment:
- [ ] ✓ Service running continuously (uptime > 99%)
- [ ] ✓ API response time < 1 second
- [ ] ✓ CPU usage < 60% average
- [ ] ✓ Memory usage < 70% average
- [ ] ✓ Disk usage < 80%
- [ ] ✓ All endpoints responding correctly
- [ ] ✓ SSL certificate valid
- [ ] ✓ CloudWatch metrics collecting data
- [ ] ✓ Logs properly recorded and accessible

---

## Deployment Sign-Off

- **Deployment Date**: ___________
- **Deployed By**: ___________
- **Instance ID**: ___________
- **Public IP**: ___________
- **Domain**: ___________
- **API Key**: ___________
- **Notes**: ___________

