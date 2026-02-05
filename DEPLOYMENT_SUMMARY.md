# EC2 Deployment - Complete Guide Summary

## 📚 Documentation Files Created

| File | Purpose | Read Time |
|------|---------|-----------|
| **DEPLOYMENT_GUIDE.md** | Comprehensive step-by-step deployment guide | 15 min |
| **AWS_EC2_DEPLOYMENT.md** | AWS-specific infrastructure and setup | 20 min |
| **DOCKER_DEPLOYMENT.md** | Docker containerization and deployment | 15 min |
| **EC2_QUICK_REFERENCE.md** | Commands and quick lookup reference | 10 min |
| **DEPLOYMENT_CHECKLIST.md** | Pre/during/post deployment checklist | 10 min |
| **deploy.sh** | Automated one-click deployment script | N/A |
| **manual-deploy.sh** | Interactive step-by-step script | N/A |

---

## 🚀 Quick Start (Choose Your Path)

### Path 1: Automated Deployment (Easiest) ⚡
**Time: 30-45 minutes**

```bash
# 1. Create EC2 instance
aws ec2 run-instances --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.large --key-name scam-honeypot-key \
  --security-group-ids sg-xxx --region us-east-1

# 2. SSH into instance
ssh -i scam-honeypot-key.pem ubuntu@<EC2-PUBLIC-IP>

# 3. Run deployment script
curl -O https://raw.githubusercontent.com/your-repo/main/deploy.sh
bash deploy.sh your-domain.com "strong-api-key"

# 4. Verify
curl http://localhost:8000/health
```

### Path 2: Manual Step-by-Step ✋
**Time: 45-60 minutes**

Follow DEPLOYMENT_GUIDE.md steps 1-10 in order:
1. Initial server setup
2. Clone & Python environment
3. Environment configuration
4. Download models
5. Systemd service
6. Nginx setup
7. SSL certificate
8. Monitoring
9. Health check
10. Backup strategy

### Path 3: Docker Deployment 🐳
**Time: 15-20 minutes** (if Docker image pre-built)

```bash
# Build Docker image
docker build -f backend/Dockerfile -t scam-honeypot:latest .

# Run container
docker run -d -p 8000:8000 \
  -e API_SECRET_KEY=your-key \
  scam-honeypot:latest

# Or use Docker Compose
docker-compose up -d
```

---

## 📋 Pre-Deployment Checklist

Before starting, ensure you have:

- [ ] AWS account with billing alerts
- [ ] EC2 key pair downloaded and secured (`chmod 400`)
- [ ] Security group created with ports 22, 80, 443 open
- [ ] Repository cloned and tested locally
- [ ] `.env.example` reviewed
- [ ] Domain name (optional but recommended)
- [ ] SSL certificate plan (Let's Encrypt or AWS ACM)
- [ ] Estimated budget: $80-150/month

---

## 🏗️ Architecture Overview

```
Internet
    ↓
Route 53 (DNS)
    ↓
CloudFront (Optional CDN)
    ↓
Application Load Balancer
    ↓
EC2 Security Group (Firewall)
    ↓
┌─────────────────────────────────────┐
│        EC2 Instance (Ubuntu)         │
│  ┌──────────────────────────────┐   │
│  │ Nginx (Reverse Proxy)         │   │
│  │ Port 80/443                   │   │
│  └──────────────────────────────┘   │
│           ↓                          │
│  ┌──────────────────────────────┐   │
│  │ Gunicorn + Uvicorn Workers    │   │
│  │ Port 8000 (Internal)          │   │
│  │ 2-4 worker processes          │   │
│  └──────────────────────────────┘   │
│           ↓                          │
│  ┌──────────────────────────────┐   │
│  │ FastAPI Application           │   │
│  │ • ASR (Whisper)              │   │
│  │ • Detection (DistilBERT)     │   │
│  │ • Extraction (spaCy)         │   │
│  │ • Engagement (Phi-2)         │   │
│  │ • TTS (Tacotron2)            │   │
│  └──────────────────────────────┘   │
│                                      │
│  Volumes: /models, /logs             │
└─────────────────────────────────────┘
    ↓
CloudWatch (Monitoring)
SNS (Alerts)
```

---

## ⏱️ Timeline Estimates

| Task | Time | Notes |
|------|------|-------|
| AWS setup | 10 min | Create SG, key pair |
| EC2 launch | 2 min | Wait 1-2 min for boot |
| SSH & dependencies | 5 min | apt update/install |
| Clone & setup | 5 min | venv, pip install |
| **Download models** | **15-30 min** | ⏳ Longest step |
| Systemd & Nginx | 5 min | Copy configs |
| SSL certificate | 3 min | Let's Encrypt |
| **Total** | **~45 min** | **+ model download time** |

---

## 🔑 Key Configuration Values

Create a secure document with these values:

```
Instance ID: i-xxxxxxxxxxxxx
Public IP: 18.234.56.78
Domain: api.your-domain.com
API Key: sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
SSH Key: /path/to/scam-honeypot-key.pem
Nginx Config: /etc/nginx/sites-available/scam-honeypot
Service: /etc/systemd/system/scam-honeypot.service
Logs: sudo journalctl -u scam-honeypot -f
```

---

## 🔒 Security Considerations

### Essential
- [ ] Change `API_SECRET_KEY` to strong random value
- [ ] Restrict CORS to your domain only
- [ ] Use SSH keys only (no password login)
- [ ] Enable SSL/TLS certificates
- [ ] Configure Security Group properly

### Recommended
- [ ] Enable CloudWatch monitoring
- [ ] Set up automated backups
- [ ] Configure security group to minimize open ports
- [ ] Use IAM roles for AWS access
- [ ] Enable VPC encryption

### Optional (Enterprise)
- [ ] Web Application Firewall (WAF)
- [ ] DDoS protection (Shield)
- [ ] Intrusion Detection System (IDS)
- [ ] Multi-region redundancy
- [ ] Database backup automation

---

## 📊 Monitoring & Alerts

### Default CloudWatch Metrics
- CPU Utilization
- Memory Usage
- Disk Usage
- Network In/Out
- Application Logs

### Recommended Alarms
- **CPU > 80%** for 5 minutes
- **Memory > 80%** for 5 minutes
- **Disk > 85%** for 5 minutes
- **Service Failed** - Custom metric
- **API Response Time > 2s** - Custom metric

### Logging
- **Application**: `sudo journalctl -u scam-honeypot -f`
- **Nginx**: `/var/log/nginx/access.log` and `error.log`
- **System**: `/var/log/syslog`
- **CloudWatch**: `/aws/ec2/scam-honeypot`

---

## 💰 Cost Breakdown (Monthly)

| Service | Instance Type | Cost |
|---------|---------------|------|
| **EC2 Compute** | t3.large | $60 |
| **EBS Storage** | 50GB gp3 | $5 |
| **Data Transfer** | Out | $10 |
| **CloudWatch** | Logs + Metrics | $10 |
| **Route 53** | DNS | $1 |
| **SSL Certificate** | Let's Encrypt | FREE |
| **Total** | | **~$86/month** |

### Cost Optimization
- Use `t3.medium` (-$30) for development
- Use Spot instances (-70%) for non-critical
- Reserved instances (-30-40%) for 1-3 years
- Remove unused EBS volumes

---

## 🆘 Troubleshooting Quick Links

### Service Issues
- **Won't start**: Check logs → `sudo journalctl -u scam-honeypot -n 100`
- **High CPU/Memory**: Reduce workers, check logs for loops
- **Models not loading**: Re-run `download_models.py`
- **Port conflicts**: `sudo lsof -i :8000`

### Network Issues
- **SSL errors**: Check certificate path, dates → `sudo certbot certificates`
- **DNS not resolving**: Wait 5 minutes, verify Route 53, run `nslookup`
- **Nginx errors**: Check config → `sudo nginx -t`
- **Connection timeout**: Check Security Group, EC2 IP

### Database/Backup Issues
- **Models missing**: Backup EBS volume → Restore from snapshot
- **Logs overflowing**: `journalctl --vacuum=1w`
- **Low disk space**: Clean logs, increase volume size

---

## 📞 Support Resources

### Official Documentation
- **AWS EC2**: https://docs.aws.amazon.com/ec2/
- **FastAPI**: https://fastapi.tiangolo.com/
- **Nginx**: https://nginx.org/en/docs/
- **Let's Encrypt**: https://letsencrypt.org/docs/

### Useful Tools
- **AWS CLI**: AWS command-line interface
- **CloudWatch**: AWS monitoring dashboard
- **SSH**: Remote terminal access
- **curl**: Test API endpoints
- **systemctl**: Service management

### Team Communication
- Create Slack channel: #scam-honeypot-deployment
- Document access credentials in password manager
- Share runbooks with team
- Schedule maintenance windows

---

## ✅ Post-Deployment Verification

### Immediate (5 minutes)
```bash
# 1. Service running
sudo systemctl status scam-honeypot

# 2. No errors in logs
sudo journalctl -u scam-honeypot | grep ERROR

# 3. Health check
curl http://localhost:8000/health
```

### First Day (1 hour after deployment)
```bash
# 1. CPU/Memory normal
top -u ubuntu

# 2. Disk space available
df -h

# 3. API responding
curl https://your-domain.com/api/v1/extract \
  -H "x-api-key: your-key" \
  -d '{"transcript":"test"}'
```

### First Week
- [ ] CloudWatch metrics collecting data
- [ ] No unexpected errors in logs
- [ ] DNS resolving correctly
- [ ] SSL certificate valid
- [ ] Backup procedure tested

---

## 🎓 Learning Path

1. **Start Here**: Read DEPLOYMENT_CHECKLIST.md (10 min)
2. **Choose Path**: Pick automated, manual, or Docker (decide in 2 min)
3. **Follow Guide**: Execute chosen deployment path (30-45 min)
4. **Monitor**: Review logs and metrics (ongoing)
5. **Troubleshoot**: Use EC2_QUICK_REFERENCE.md as needed
6. **Optimize**: Review AWS_EC2_DEPLOYMENT.md for advanced features

---

## 📝 Next Steps

### Immediate (After deployment)
- [ ] Save credentials in password manager
- [ ] Share access with team members
- [ ] Create runbook for operations
- [ ] Schedule status check meeting

### Week 1
- [ ] Review CloudWatch metrics
- [ ] Test auto-scaling (if configured)
- [ ] Verify backup procedure
- [ ] Load test the API

### Month 1
- [ ] Review costs and optimize
- [ ] Implement advanced monitoring
- [ ] Plan disaster recovery drill
- [ ] Document lessons learned

### Quarterly
- [ ] Security audit
- [ ] Update dependencies
- [ ] Performance optimization
- [ ] Capacity planning

---

## 🎉 Success Criteria

Your deployment is successful when:

✅ Application accessible via `https://your-domain.com`
✅ Health check returns success: `{"status":"success",...}`
✅ All API endpoints responding
✅ CloudWatch monitoring active
✅ SSL certificate valid (no warnings)
✅ Logs clean (no ERROR level entries)
✅ CPU < 60%, Memory < 70%, Disk < 80%
✅ Service auto-restarts on failure
✅ Team can access and manage service
✅ Backup procedure documented and tested

---

## 📖 Document Quick Links

- [Full Deployment Guide](./DEPLOYMENT_GUIDE.md) - 10+ hour read
- [AWS EC2 Specific](./AWS_EC2_DEPLOYMENT.md) - AWS-focused
- [Docker Option](./DOCKER_DEPLOYMENT.md) - Container deployment
- [Quick Reference](./EC2_QUICK_REFERENCE.md) - Commands & troubleshooting
- [Deployment Checklist](./DEPLOYMENT_CHECKLIST.md) - Step-by-step checklist

---

## Questions?

Refer to appropriate guide:
- **"How do I deploy?"** → DEPLOYMENT_GUIDE.md
- **"What's the AWS way?"** → AWS_EC2_DEPLOYMENT.md
- **"I want Docker"** → DOCKER_DEPLOYMENT.md
- **"I need a command"** → EC2_QUICK_REFERENCE.md
- **"What's my checklist?"** → DEPLOYMENT_CHECKLIST.md

Good luck with your deployment! 🚀
