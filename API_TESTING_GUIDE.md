# API Testing Guide - PowerShell

## Server Status
✅ **Server is running** on `http://localhost:8000`

## Authentication
- **API Key**: `sk_test_123456789`
- **Header**: `x-api-key`

---

## 1. Health Check
```powershell
$response = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method GET
$response | ConvertTo-Json
```

**Response:**
```json
{
  "status": "success",
  "message": "Service is healthy",
  "timestamp": "2026-02-05T09:45:15.889726+00:00"
}
```

---

## 2. Scam Detection
Detect if a transcript contains scam indicators.

```powershell
$headers = @{
    "Content-Type" = "application/json"
    "x-api-key" = "sk_test_123456789"
}
$body = @{
    "transcript" = "Send OTP now from bank!"
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/detect" `
    -Method POST `
    -Headers $headers `
    -Body $body

$response | ConvertTo-Json
```

---

## 3. Extract Entities
Extract contact info, payment methods, and scammer intelligence from text.

```powershell
$headers = @{
    "Content-Type" = "application/json"
    "x-api-key" = "sk_test_123456789"
}
$body = @{
    "transcript" = "UPI: scam@paytm, phone: +919876543210"
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/extract" `
    -Method POST `
    -Headers $headers `
    -Body $body `
    -TimeoutSec 10

$response | ConvertTo-Json
```

**Response (Partial):**
```json
{
  "status": "success",
  "entities": {
    "phone_numbers": ["+919876543210"],
    "upi_ids": ["scam@paytm"]
  },
  "scammer_intelligence": {
    "contact_info": {
      "phone_numbers": "+919876543210",
      "upi_ids": "scam@paytm"
    },
    "total_entities_found": 3
  },
  "confidence_scores": {
    "overall": 0.93
  }
}
```

---

## 4. Engage (Text Conversation)
Start a text-based conversation with the scam honeypot.

```powershell
$params = @{
    Uri = "http://localhost:8000/api/v1/engage"
    Method = "POST"
    Headers = @{"x-api-key" = "sk_test_123456789"}
    Form = @{
        "session_id" = "test_session_1"
        "text" = "Your account blocked, share UPI"
    }
}

$response = Invoke-RestMethod @params
$response | ConvertTo-Json
```

---

## 5. Full Pipeline
Process an audio file through the complete pipeline (ASR → Detection → Engagement).

```powershell
# Create a test audio file first (or use an existing one)
$audioFilePath = "C:\path\to\audio.wav"

$params = @{
    Uri = "http://localhost:8000/api/v1/full-pipeline"
    Method = "POST"
    Headers = @{"x-api-key" = "sk_test_123456789"}
    Form = @{
        "audio" = Get-Item -Path $audioFilePath
        "session_id" = "test_full_1"
    }
}

$response = Invoke-RestMethod @params
$response | ConvertTo-Json
```

---

## Important Notes

### PowerShell vs curl
- **PowerShell** uses `Invoke-RestMethod` (not `curl` syntax)
- The `-X`, `-H`, `-d`, `-F` flags used in curl don't work in PowerShell
- Use hashtables (`@{}`) for headers and form data

### Timeout
- Some requests may take longer (models loading)
- Use `-TimeoutSec 30` for longer operations

### Error Handling
```powershell
try {
    $response = Invoke-RestMethod @params
    $response | ConvertTo-Json
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
```

---

## Server Status Details
- **Health Check**: ✅ Working
- **Extract Entity**: ✅ Working
- **Scam Detection**: Requires testing with full transcript
- **Engagement**: Text-based conversation support
- **Full Pipeline**: Audio processing support

## Known Issues
- Some models have validation warnings (NLI, Voice Detector, LLM)
- Server uses lazy-loading for failed models on first request
