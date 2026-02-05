"""Agentic conversation controller for scam engagement."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.core.config import settings
from app.core.logger import get_logger
from app.models.model_loader import get_model_loader

logger = get_logger("pipeline.agent")


class AgenticController:
    """
    Stateful agentic controller for engaging scam callers.

    Maintains per-session conversation memory, applies safety constraints,
    and extracts intelligence from user inputs.
    """

    SYSTEM_PROMPT = (
        "You are a cooperative elderly person who is slightly confused but willing to help. "
        "Never ask for OTP, passwords, credit card numbers, or bank account details. "
        "Never provide real personal information like addresses, real phone numbers, or financial data. "
        "Engage naturally with the caller while subtly extracting information they volunteer "
        "(phone numbers, organization names, payment methods). "
        "Keep responses short (2-3 sentences), natural, and slightly hesitant."
    )

    SAFETY_PATTERNS = [
        (re.compile(r"\b(OTP|one\s*time\s*password|verification\s*code)\b", re.IGNORECASE),
         "I'm not sure about that. Could you tell me more about your organization?"),
        (re.compile(r"\b(bank\s*account|account\s*number|routing\s*number|IFSC)\b", re.IGNORECASE),
         "I don't remember that right now. Could you explain the process again?"),
        (re.compile(r"\b(password|PIN|passcode)\b", re.IGNORECASE),
         "I'm not comfortable sharing that. Can you tell me more about who you are?"),
        (re.compile(r"\b(CVV|CVC|card\s*number|credit\s*card|debit\s*card|expiry|expiration)\b", re.IGNORECASE),
         "I'm not comfortable with card details. Could you tell me more about your organization?"),
        (re.compile(r"\b(SSN|social\s*security|PAN|Aadhaar|Aadhar|ID\s*number|passport|driver'?s\s*license)\b", re.IGNORECASE),
         "I don't have those details handy. Can you explain what this is for?"),
        (re.compile(r"\b(address|home\s*address|mailing\s*address|residential\s*address)\b", re.IGNORECASE),
         "I'd rather not share my address. Could you tell me more about your company?"),
        (re.compile(r"\b(email|e-mail)\b", re.IGNORECASE),
         "I'm not sure about my email right now. Could you explain the process again?"),
        (re.compile(r"\b(KYC|identity\s*document|ID\s*proof|verification\s*document)\b", re.IGNORECASE),
         "I'm not comfortable sharing documents. Can you tell me more about your organization?"),
    ]

    NUMERIC_LEAK_PATTERN = re.compile(r"\b\d{9,19}\b")

    EXTRACTION_PATTERNS = {
        "upi": re.compile(r"\b[\w.\-]+@[\w]+\b"),
        "phone": re.compile(r"\b(\+91[\-\s]?)?[6-9]\d{9}\b"),
        "url": re.compile(r"https?://[^\s]+"),
    }

    ORG_KEYWORDS = ["bank", "company", "limited", "ltd", "pvt", "inc", "corp", "agency", "department"]

    MAX_RESPONSE_LENGTH = 150

    def __init__(self, device: Optional[str] = None) -> None:
        """Initialize AgenticController."""
        self.device = device or settings.DEVICE
        self.logger = get_logger("pipeline.agent")
        self._llm_model = None
        self._llm_tokenizer = None
        self._sessions: Dict[str, Dict[str, Any]] = {}

        self.logger.info(f"AgenticController initialized with device: {self.device}")

    def _load_model(self) -> None:
        """Lazy-load LLM model unless API mode is enabled."""
        if settings.LLM_USE_API:
            if not settings.LLM_API_BASE_URL or not settings.LLM_API_KEY:
                raise ValueError("LLM API mode enabled but API base URL or key is missing")
            return

        if self._llm_model is not None and self._llm_tokenizer is not None:
            return

        try:
            model_loader = get_model_loader()
            self._llm_model, self._llm_tokenizer = model_loader.get_llm_model()

            if self._llm_model is None or self._llm_tokenizer is None:
                raise RuntimeError("LLM model or tokenizer not loaded")

        except FileNotFoundError as e:
            self.logger.error("LLM model not found. Run: python scripts/download_models.py")
            raise FileNotFoundError(
                "LLM model not downloaded. Run 'python scripts/download_models.py'"
            ) from e

        except Exception as e:
            self.logger.error(f"Failed to load LLM model: {e}")
            raise RuntimeError(f"Could not load LLM model: {e}") from e

    def _get_or_create_session(self, session_id: str) -> Dict[str, Any]:
        """Retrieve or create session state for a session_id."""
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "history": [],
                "turn_count": 0,
                "terminated": False,
                "extracted_info": [],
                "created_at": time.time(),
                "last_active": time.time(),
            }
            self.logger.info(f"Created new session: {session_id}")
        return self._sessions[session_id]

    def _build_conversation_context(
        self,
        session_id: str,
        user_input: str
    ) -> Tuple[str, List[Dict[str, str]]]:
        """Build prompt string and message list for generation."""
        session = self._get_or_create_session(session_id)
        history = session.get("history", [])

        # Limit memory to last N turns
        max_turns = settings.AGENT_MAX_MEMORY_TURNS
        recent_history = history[-max_turns:]

        # Build prompt string
        prompt_lines = [f"System: {self.SYSTEM_PROMPT}"]
        for turn in recent_history:
            prompt_lines.append(f"User: {turn['user']}")
            prompt_lines.append(f"Assistant: {turn['assistant']}")
        prompt_lines.append(f"User: {user_input}")
        prompt_lines.append("Assistant:")
        prompt = "\n".join(prompt_lines)

        # Build OpenAI-compatible message list
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        for turn in recent_history:
            messages.append({"role": "user", "content": turn["user"]})
            messages.append({"role": "assistant", "content": turn["assistant"]})
        messages.append({"role": "user", "content": user_input})

        return prompt, messages

    def _generate_response_local(self, prompt: str) -> str:
        """Generate response using local LLM model."""
        import torch

        self._load_model()

        inputs = self._llm_tokenizer(prompt, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        pad_token_id = self._llm_tokenizer.eos_token_id
        if pad_token_id is None:
            pad_token_id = self._llm_tokenizer.pad_token_id

        outputs = self._llm_model.generate(
            **inputs,
            max_new_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
            do_sample=True,
            pad_token_id=pad_token_id,
        )

        generated = self._llm_tokenizer.decode(outputs[0], skip_special_tokens=True)

        # Extract assistant response by removing prompt prefix
        if generated.startswith(prompt):
            return generated[len(prompt):].strip()

        # Fallback: attempt to split on last "Assistant:" marker
        if "Assistant:" in generated:
            return generated.split("Assistant:")[-1].strip()

        return generated.strip()

    def _generate_response_api(self, messages: List[Dict[str, str]]) -> str:
        """Generate response using OpenAI-compatible API."""
        if not settings.LLM_API_BASE_URL or not settings.LLM_API_KEY:
            raise ValueError("LLM API base URL or key not configured")

        url = settings.LLM_API_BASE_URL.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.LLM_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.LLM_MODEL_NAME,
            "messages": messages,
            "max_tokens": settings.LLM_MAX_TOKENS,
            "temperature": settings.LLM_TEMPERATURE,
        }

        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("LLM API returned no choices")

        return choices[0]["message"]["content"].strip()

    def _check_termination(self, user_input: str, session_id: str) -> bool:
        """Check termination keywords and session flags."""
        session = self._get_or_create_session(session_id)
        if session.get("terminated"):
            return True

        lowered = user_input.lower()
        for keyword in settings.AGENT_TERMINATION_KEYWORDS:
            if keyword.lower() in lowered:
                return True

        return False

    def _should_trigger_callback(self, session_id: str) -> bool:
        """Decide whether final callback should be sent for a session."""
        session = self._get_or_create_session(session_id)
        # If already terminated, trigger
        if session.get("terminated"):
            return True

        # If we've exceeded max turns (trigger when > configured threshold)
        if session.get("turn_count", 0) > settings.AGENT_MAX_TURNS_FOR_CALLBACK:
            return True

        # If we have extracted intelligence of >= 2 different types and min turns reached
        types = {item.get("type") for item in session.get("extracted_info", [])}
        if len([t for t in types if t]) >= 2 and session.get("turn_count", 0) >= settings.AGENT_MIN_TURNS_FOR_CALLBACK:
            return True

        return False

    def _generate_agent_notes(self, session: Dict[str, Any]) -> str:
        """Generate a short human-readable summary of scammer tactics from session."""
        notes = []
        extracted = session.get("extracted_info", [])
        types = {item.get("type") for item in extracted}
        if "upi" in types:
            notes.append("Scammer requested payment via UPI")
        if "phone" in types:
            notes.append("Exchange of phone numbers observed")
        # Check for urgency keywords in recent history
        history_text = " ".join([turn.get("user", "") + " " + turn.get("assistant", "") for turn in session.get("history", [])])
        if re.search(r"\b(urgent|immediately|verify|confirm|blocked|suspended)\b", history_text, re.IGNORECASE):
            notes.append("Urgency tactics used")
        if not notes:
            notes.append("No clear payment requests observed; normal engagement")
        return "; ".join(notes)

    def send_final_callback(self, session_id: str, scam_detected: bool = True) -> Optional[Dict[str, Any]]:
        """Send final honeypot result to the GUVI evaluation endpoint."""
        session = self._get_or_create_session(session_id)

        if session.get("callback_sent"):
            self.logger.info(f"Callback already sent for session: {session_id}")
            return None

        if not settings.GUVI_CALLBACK_ENABLED:
            self.logger.info("GUVI callback disabled by configuration")
            return None

        total_messages = int(session.get("turn_count", 0))

        # Aggregate intelligence
        bank_accounts = set()
        upi_ids = set()
        phishing_links = set()
        phone_numbers = set()
        suspicious_keywords = set()

        for item in session.get("extracted_info", []):
            t = item.get("type")
            v = item.get("value")
            if not v:
                continue
            if t == "upi":
                upi_ids.add(v)
            elif t == "phone":
                phone_numbers.add(v)
            elif t == "url" or t == "url":
                phishing_links.add(v)
            elif t == "account":
                bank_accounts.add(v)
            else:
                # Catch-all: numbers that look like accounts
                if re.fullmatch(r"\d{9,18}", str(v)):
                    bank_accounts.add(v)

        # Use extractor for suspicious keywords if available
        try:
            from app.pipeline.extractor import get_entity_extractor

            extractor = get_entity_extractor()
            # Look through recent history text for suspicious keywords
            history_text = " ".join([turn.get("user", "") for turn in session.get("history", [])])
            kws = extractor._extract_suspicious_keywords(history_text)
            for k in kws:
                suspicious_keywords.add(k)
        except Exception:
            # Fallback: simple keyword scan
            history_text = " ".join([turn.get("user", "") for turn in session.get("history", [])])
            if re.search(r"\b(urgent|immediately|verify|blocked|suspended|otp)\b", history_text, re.IGNORECASE):
                suspicious_keywords.add("urgency")

        payload = {
            "sessionId": session_id,
            "scamDetected": bool(scam_detected),
            "totalMessagesExchanged": total_messages,
            "extractedIntelligence": {
                "bankAccounts": list(bank_accounts),
                "upiIds": list(upi_ids),
                "phishingLinks": list(phishing_links),
                "phoneNumbers": list(phone_numbers),
                "suspiciousKeywords": list(suspicious_keywords),
            },
            "agentNotes": self._generate_agent_notes(session),
        }

        self.logger.debug(f"Sending GUVI callback for session {session_id}: {payload}")

        try:
            resp = requests.post(
                settings.GUVI_CALLBACK_URL,
                json=payload,
                timeout=int(settings.GUVI_CALLBACK_TIMEOUT),
            )
            if resp.ok:
                session["callback_sent"] = True
                self.logger.info(f"GUVI callback succeeded for session {session_id}: {resp.status_code}")
                try:
                    return resp.json()
                except Exception:
                    return {"status_code": resp.status_code}
            else:
                self.logger.warning(f"GUVI callback failed ({resp.status_code}): {resp.text}")
                return None

        except Exception as e:
            self.logger.error(f"GUVI callback error for session {session_id}: {e}")
            return None

    def _apply_safety_filter(self, response: str) -> str:
        """Filter unsafe responses and replace with safe fallback."""
        for pattern, fallback in self.SAFETY_PATTERNS:
            if pattern.search(response):
                self.logger.warning("Safety filter triggered; replacing response")
                return fallback
        if self.NUMERIC_LEAK_PATTERN.search(response):
            self.logger.warning("Numeric leak pattern detected; replacing response")
            return "I don't have those numbers. Could you explain the process again?"
        return response

    def _extract_intelligence_from_input(self, user_input: str) -> List[Dict[str, Any]]:
        """Extract intelligence such as phone numbers, UPI IDs, and URLs from user input."""
        extracted = []

        for kind, pattern in self.EXTRACTION_PATTERNS.items():
            for match in pattern.findall(user_input):
                value = match if isinstance(match, str) else match[0]
                extracted.append({"type": kind, "value": value, "confidence": 0.9})

        # Attempt to extract bank/account numbers using EntityExtractor regex logic
        try:
            from app.pipeline.extractor import get_entity_extractor

            extractor = get_entity_extractor()
            patterns = extractor._extract_regex_patterns(user_input)
            for acct in patterns.get("account_numbers", []):
                extracted.append({"type": "account", "value": acct, "confidence": 0.8})
        except Exception:
            # If extractor unavailable, attempt a simple regex as fallback
            try:
                acct_matches = re.findall(r"\b\d{9,18}\b", user_input)
                for acct in acct_matches:
                    extracted.append({"type": "account", "value": acct, "confidence": 0.6})
            except Exception:
                pass

        lowered = user_input.lower()
        if any(keyword in lowered for keyword in self.ORG_KEYWORDS):
            extracted.append({"type": "organization", "value": user_input, "confidence": 0.5})

        return extracted

    def engage(
        self,
        session_id: str,
        user_input: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Main entry point for generating agent response."""
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        if not user_input or not user_input.strip():
            raise ValueError("user_input must be a non-empty string")

        session = self._get_or_create_session(session_id)
        session["last_active"] = time.time()

        # Optionally seed history with external conversation_history
        if conversation_history and not session["history"]:
            for item in conversation_history[-settings.AGENT_MAX_MEMORY_TURNS:]:
                user_text = item.get("user") or item.get("content") or ""
                assistant_text = item.get("assistant") or item.get("response") or ""
                if user_text and assistant_text:
                    session["history"].append({"user": user_text, "assistant": assistant_text})

        if self._check_termination(user_input, session_id):
            # Treat terminating input like a normal turn: record history, extract intelligence,
            # increment turn count, then mark terminated and trigger callback.
            response_text = "Thank you for calling. Goodbye."

            # Update session with final exchange
            session["history"].append({"user": user_input, "assistant": response_text})
            session["turn_count"] += 1

            # Extract intelligence from the terminating input
            try:
                extracted = self._extract_intelligence_from_input(user_input)
                if extracted:
                    session["extracted_info"].extend(extracted)
                    self.logger.debug(f"Extracted intelligence on termination: {extracted}")
            except Exception as e:
                self.logger.exception(f"Intelligence extraction failed on termination: {e}")

            session["terminated"] = True

            # Trigger callback if conditions met and not already sent
            try:
                if self._should_trigger_callback(session_id) and not session.get("callback_sent"):
                    self.send_final_callback(session_id, scam_detected=True)
            except Exception:
                self.logger.exception("Callback trigger failed during termination flow")

            return {
                "transcript": user_input,
                "agent_response_text": response_text,
                "agent_response_audio": None,
                "session_id": session_id,
                "turn_number": session["turn_count"],
                "terminated": True,
                "extracted_intelligence": session.get("extracted_info", []),
                "callback_sent": session.get("callback_sent", False),
            }

        prompt, messages = self._build_conversation_context(session_id, user_input)

        try:
            if settings.LLM_USE_API:
                response_text = self._generate_response_api(messages)
            else:
                response_text = self._generate_response_local(prompt)

        except Exception as e:
            self.logger.error(f"Generation failed: {e}")
            response_text = "I'm not sure I understand. Could you explain that again?"

        response_text = self._apply_safety_filter(response_text)

        # Update session
        session["history"].append({"user": user_input, "assistant": response_text})
        session["turn_count"] += 1

        extracted = self._extract_intelligence_from_input(user_input)
        if extracted:
            session["extracted_info"].extend(extracted)
            self.logger.debug(f"Extracted intelligence: {extracted}")
        # Check and trigger callback if thresholds/conditions met
        try:
            if self._should_trigger_callback(session_id) and not session.get("callback_sent"):
                self.send_final_callback(session_id, scam_detected=True)
        except Exception:
            self.logger.exception("Callback trigger failed after engagement")

        return {
            "transcript": user_input,
            "agent_response_text": response_text,
            "agent_response_audio": None,
            "session_id": session_id,
            "turn_number": session["turn_count"],
            "terminated": False,
            "extracted_intelligence": session.get("extracted_info", []),
            "callback_sent": session.get("callback_sent", False),
        }

    def engage_demo(
        self,
        session_id: str,
        user_input: str,
        mock_response: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Demo mode engagement without loading models."""
        if settings.DEMO_MODE:
            if mock_response:
                response_text = mock_response
            else:
                lowered = user_input.lower()
                if "payment" in lowered:
                    response_text = "Oh, I see. What payment method do you prefer?"
                elif "account" in lowered:
                    response_text = "I'm a bit confused about accounts. Can you explain more?"
                else:
                    response_text = "That's interesting. Tell me more about your organization."

            return {
                "transcript": user_input,
                "agent_response_text": response_text,
                "agent_response_audio": None,
                "session_id": session_id,
                "turn_number": 1,
                "terminated": False,
                "extracted_intelligence": [
                    {"type": "phone", "value": "9876543210", "confidence": 0.85}
                ],
            }

        return self.engage(session_id, user_input)

    def terminate_session(self, session_id: str) -> Dict[str, Any]:
        """Manually terminate a session and return summary."""
        session = self._get_or_create_session(session_id)
        session["terminated"] = True
        self.logger.info(f"Session terminated: {session_id}")

        # Send final callback if not already sent
        try:
            if not session.get("callback_sent") and self._should_trigger_callback(session_id):
                self.send_final_callback(session_id, scam_detected=True)
        except Exception:
            self.logger.exception("Callback trigger failed during manual termination")

        return {
            "session_id": session_id,
            "terminated": True,
            "extracted_intelligence": session.get("extracted_info", []),
            "callback_sent": session.get("callback_sent", False),
        }

    def get_session_info(self, session_id: str) -> Dict[str, Any]:
        """Return session metadata for debugging and monitoring."""
        session = self._get_or_create_session(session_id)
        return {
            "session_id": session_id,
            "turn_count": session.get("turn_count", 0),
            "history_length": len(session.get("history", [])),
            "extracted_info_count": len(session.get("extracted_info", [])),
            "terminated": session.get("terminated", False),
        }

    def clear_old_sessions(self, max_age_seconds: int = 3600) -> int:
        """Remove inactive sessions older than max_age_seconds."""
        now = time.time()
        to_remove = [
            sid for sid, s in self._sessions.items()
            if now - s.get("last_active", now) > max_age_seconds
        ]
        for sid in to_remove:
            del self._sessions[sid]
        if to_remove:
            self.logger.info(f"Cleared {len(to_remove)} old sessions")
        return len(to_remove)


_agent_instance: Optional[AgenticController] = None


def get_agentic_controller() -> AgenticController:
    """Get the global AgenticController singleton instance."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = AgenticController()
    return _agent_instance
