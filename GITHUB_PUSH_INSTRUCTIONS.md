# Push to GitHub - Quick Instructions

## Your Repository
- **URL**: https://github.com/SaketSinghRajput/honeycomb.git
- **Branch**: main (default)

## Steps to Push

### Step 1: Add GitHub as Remote
```bash
cd "f:\STARTUPS\buildathon-ai impact\codefiles"
git remote add origin https://github.com/SaketSinghRajput/honeycomb.git
```

### Step 2: Set Branch to Main
```bash
git branch -M main
```

### Step 3: Push to GitHub
```bash
git push -u origin main
```

## If Using SSH (Recommended for security)
```bash
# First, add SSH remote instead:
git remote add origin git@github.com:SaketSinghRajput/honeycomb.git

# Then push:
git push -u origin main
```

## What's Being Committed

✅ **Included**:
- Backend FastAPI application
- All Python source code
- Requirements.txt
- Configuration files (.env.example)
- Dockerfile and docker-compose
- Deployment guides (8 comprehensive docs)
- Scripts (deploy.sh, manual-deploy.sh)
- API testing guide
- Nginx configuration
- Systemd service file

❌ **Excluded** (via .gitignore):
- `/backend/models/` - Large pre-trained models (Whisper, Phi-2, DistilBERT, TTS, etc.)
- `.env` - Sensitive credentials
- `venv/` - Virtual environment
- `logs/` - Application logs
- `__pycache__/` - Python cache
- Audio files (*.wav, *.mp3)
- Other temporary files

## Repository Size
- **With models**: ~15-20GB (too large for GitHub)
- **Without models**: ~200-300MB (optimal)

Users can download models using:
```bash
cd backend
python scripts/download_models.py
```

## After Pushing

### Update Deployment Scripts
The deploy.sh script already references:
```bash
git clone https://github.com/your-username/buildathon-ai-impact.git .
```

Update this in deploy.sh to:
```bash
git clone https://github.com/SaketSinghRajput/honeycomb.git .
```

### Set Repository Description (GitHub)
1. Go to https://github.com/SaketSinghRajput/honeycomb
2. Click Settings
3. Edit description:
   ```
   Scam Detection AI Honeypot - FastAPI backend with Whisper ASR, NLP detection, and voice engagement
   ```
4. Add topics: `ai`, `scam-detection`, `fastapi`, `nlp`, `voice-ai`

## Verify Push Success
```bash
# Check remote
git remote -v

# View commit log
git log --oneline

# Verify GitHub
# Visit: https://github.com/SaketSinghRajput/honeycomb
```

## Future Pushes
```bash
# Make changes
git add .
git commit -m "Your commit message"
git push
```

## Important Notes

1. **Model Download**: Users need to run `python scripts/download_models.py` after cloning
2. **Environment Setup**: Users need to copy `.env.example` to `.env` and configure
3. **Virtual Environment**: Users need to create venv locally
4. **GitHub Token** (if using HTTPS):
   - Generate at: https://github.com/settings/tokens
   - Use as password when pushing

## Troubleshooting

### "Repository not found"
```bash
# Check remote URL
git remote -v

# Update if wrong
git remote remove origin
git remote add origin https://github.com/SaketSinghRajput/honeycomb.git
```

### "Permission denied"
- Use SSH key: Add key to https://github.com/settings/keys
- Or use GitHub token for HTTPS authentication

### "Everything up-to-date"
- Changes were already pushed, or no new commits
- Check with: `git status`

## Next Steps

1. ✅ **Commit done**: Your changes are committed locally
2. ⏳ **Push to GitHub**: Run the push commands above
3. 📖 **Add README**: Create GitHub README.md with project description
4. 🔗 **Update Links**: Update deploy.sh and docs with correct repo URL
5. 🏷️ **Add Tags**: Tag releases (v1.0, v1.1, etc.)
6. 📋 **Add Issues**: Create GitHub Issues for tracking tasks
