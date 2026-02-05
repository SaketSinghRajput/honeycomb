"""Entity extraction module combining spaCy NER with regex patterns."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logger import get_logger
from app.models.model_loader import get_model_loader

logger = get_logger("pipeline.extractor")


class EntityExtractor:
    """
    Extract entities and scammer intelligence from transcripts.

    Combines spaCy NER with custom regex patterns for Indian identifiers
    (UPI IDs, phone numbers, IFSC codes, etc.).
    """

    MAX_TRANSCRIPT_LENGTH = 50000
    MIN_CONFIDENCE_THRESHOLD = 0.5

    ENTITY_CATEGORIES = [
        "PERSON",
        "ORG",
        "GPE",
        "MONEY",
        "DATE",
        "TIME",
        "CARDINAL",
        "PRODUCT",
    ]

    # Regex patterns
    UPI_PATTERN = re.compile(r"\b[a-zA-Z0-9._-]+@[a-zA-Z0-9]+\b")
    PHONE_PATTERN_IN = re.compile(r"\b(\+91[-\s]?)?[6-9]\d{9}\b")
    PHONE_PATTERN_INTL = re.compile(r"\+\d{1,3}[-\s]?\d{6,14}\b")
    LANDLINE_PATTERN = re.compile(r"\b0\d{2,4}[-\s]?\d{6,8}\b")
    URL_PATTERN = re.compile(
        r"https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)"
    )
    BANK_ACCOUNT_PATTERN = re.compile(r"\b\d{9,18}\b")
    EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    IFSC_PATTERN = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")

    BANK_CONTEXT_KEYWORDS = ["account", "ifsc", "bank", "branch", "transfer"]

    def __init__(self, device: Optional[str] = None) -> None:
        """Initialize EntityExtractor."""
        self.device = device or settings.DEVICE
        self.logger = get_logger("pipeline.extractor")
        self._spacy_model = None

        self.logger.info("EntityExtractor initialized")

    def _load_model(self) -> None:
        """Lazy-load spaCy model."""
        if self._spacy_model is not None:
            return

        try:
            model_loader = get_model_loader()
            self._spacy_model = model_loader.get_spacy_model()

            if self._spacy_model is None:
                raise RuntimeError("spaCy model loaded as None")

            if not self._spacy_model.has_pipe("ner"):
                raise RuntimeError("spaCy model missing NER pipeline")

            self.logger.info("spaCy model loaded successfully")

        except FileNotFoundError as e:
            self.logger.error("spaCy model not found. Run: python scripts/download_models.py")
            raise FileNotFoundError(
                "spaCy model not downloaded. Run 'python scripts/download_models.py'"
            ) from e

        except Exception as e:
            self.logger.error(f"Failed to load spaCy model: {e}")
            raise RuntimeError(f"Could not load spaCy model: {e}") from e

    def _validate_transcript(self, transcript: str) -> None:
        """Validate transcript input."""
        if transcript is None or not isinstance(transcript, str):
            raise ValueError("Transcript must be a non-empty string")

        if not transcript.strip():
            raise ValueError("Transcript cannot be empty")

        if len(transcript) > self.MAX_TRANSCRIPT_LENGTH:
            raise ValueError(
                f"Transcript too long ({len(transcript)} chars). "
                f"Maximum length is {self.MAX_TRANSCRIPT_LENGTH} characters"
            )

    def _deduplicate_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate entities and preserve highest confidence."""
        seen = {}
        for ent in entities:
            key = (ent.get("text"), ent.get("start"), ent.get("end"))
            if key not in seen or ent.get("confidence", 0) > seen[key].get("confidence", 0):
                seen[key] = ent
        return list(seen.values())

    def _normalize_phone_number(self, phone: str) -> str:
        """Normalize phone number format."""
        normalized = re.sub(r"[\s-]", "", phone)
        if normalized.startswith("+91"):
            return normalized
        if len(normalized) == 10 and normalized[0] in "6789":
            return "+91" + normalized
        return normalized

    def _validate_bank_account(self, match: re.Match, context: str, window: int = 40) -> bool:
        """Validate bank account number with local context keywords."""
        start = max(match.start() - window, 0)
        end = min(match.end() + window, len(context))
        local_context = context[start:end].lower()
        return any(keyword in local_context for keyword in self.BANK_CONTEXT_KEYWORDS)

    def _extract_named_entities(self, transcript: str) -> Dict[str, List[Dict[str, Any]]]:
        """Extract spaCy NER entities."""
        self._load_model()

        doc = self._spacy_model(transcript)
        entities: Dict[str, List[Dict[str, Any]]] = {cat: [] for cat in self.ENTITY_CATEGORIES}

        for ent in doc.ents:
            if ent.label_ not in self.ENTITY_CATEGORIES:
                continue

            confidence = getattr(ent._, "score", 0.9)
            if confidence < self.MIN_CONFIDENCE_THRESHOLD:
                continue

            entities[ent.label_].append({
                "text": ent.text,
                "start": ent.start_char,
                "end": ent.end_char,
                "confidence": float(confidence),
            })

        # Deduplicate per category
        for category in entities:
            entities[category] = self._deduplicate_entities(entities[category])

        return entities

    def _extract_regex_patterns(self, transcript: str) -> Dict[str, List[str]]:
        """Extract regex-based entities."""
        upi_ids = [m.group(0) for m in self.UPI_PATTERN.finditer(transcript)]
        phone_numbers = []
        for pattern in [self.PHONE_PATTERN_IN, self.PHONE_PATTERN_INTL, self.LANDLINE_PATTERN]:
            for match in pattern.finditer(transcript):
                phone_numbers.append(self._normalize_phone_number(match.group(0)))
        phone_numbers = list(dict.fromkeys(phone_numbers))

        urls = [m.group(0) for m in self.URL_PATTERN.finditer(transcript)]
        emails = [m.group(0) for m in self.EMAIL_PATTERN.finditer(transcript)]
        ifsc_codes = [m.group(0) for m in self.IFSC_PATTERN.finditer(transcript)]

        account_numbers = []
        for match in self.BANK_ACCOUNT_PATTERN.finditer(transcript):
            if self._validate_bank_account(match, transcript):
                account_numbers.append(match.group(0))

        return {
            "upi_ids": list(dict.fromkeys(upi_ids)),
            "phone_numbers": phone_numbers,
            "urls": list(dict.fromkeys(urls)),
            "emails": list(dict.fromkeys(emails)),
            "ifsc_codes": list(dict.fromkeys(ifsc_codes)),
            "account_numbers": list(dict.fromkeys(account_numbers)),
        }

    def _build_scammer_intelligence(
        self,
        entities: Dict[str, List[Dict[str, Any]]],
        patterns: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        """Aggregate structured intelligence."""
        persons = [e["text"] for e in entities.get("PERSON", [])]
        orgs = [e["text"] for e in entities.get("ORG", [])]
        locations = [e["text"] for e in entities.get("GPE", [])]
        money = [e["text"] for e in entities.get("MONEY", [])]

        total_entities = sum(len(v) for v in entities.values()) + sum(
            len(v) for v in patterns.values()
        )

        high_risk = []
        if len(patterns.get("upi_ids", [])) > 1:
            high_risk.append("multiple_upi_ids")

        # Flag only truly foreign numbers (start with + but not +91)
        foreign_phones = [p for p in patterns.get("phone_numbers", []) if p.startswith("+") and not p.startswith("+91")]
        if foreign_phones:
            high_risk.append("foreign_phone_number")

        return {
            "contact_info": {
                "phone_numbers": patterns.get("phone_numbers", []),
                "emails": patterns.get("emails", []),
                "upi_ids": patterns.get("upi_ids", []),
            },
            "payment_methods": {
                "upi_ids": patterns.get("upi_ids", []),
                "account_numbers": patterns.get("account_numbers", []),
                "ifsc_codes": patterns.get("ifsc_codes", []),
            },
            "organizations": orgs,
            "locations": locations,
            "persons": persons,
            "urls": patterns.get("urls", []),
            "financial_references": money + patterns.get("account_numbers", []),
            "total_entities_found": total_entities,
            "high_risk_indicators": high_risk,
        }

    def _extract_suspicious_keywords(self, transcript: str) -> List[str]:
        """Find suspicious scam-related keywords in transcript."""
        keywords = [
            "urgent",
            "verify",
            "blocked",
            "suspended",
            "otp",
            "bank",
            "account",
            "payment",
            "refund",
            "prize",
            "winner",
            "confirm",
            "immediately",
        ]
        found = set()
        lower = transcript.lower()
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", lower):
                found.add(kw)
        return list(found)

    def get_callback_intelligence(self, transcript: str) -> Dict[str, Any]:
        """Return intelligence formatted for GUVI callback payload.

        Fields: bankAccounts, upiIds, phishingLinks, phoneNumbers, suspiciousKeywords
        """
        # Ensure transcript valid
        try:
            self._validate_transcript(transcript)
        except Exception:
            # Return empty payload on invalid transcript
            return {
                "bankAccounts": [],
                "upiIds": [],
                "phishingLinks": [],
                "phoneNumbers": [],
                "suspiciousKeywords": [],
            }

        patterns = self._extract_regex_patterns(transcript)

        bank_accounts = patterns.get("account_numbers", [])
        upi_ids = patterns.get("upi_ids", [])
        phishing_links = patterns.get("urls", [])
        phone_numbers = patterns.get("phone_numbers", [])
        suspicious_keywords = self._extract_suspicious_keywords(transcript)

        return {
            "bankAccounts": list(dict.fromkeys(bank_accounts)),
            "upiIds": list(dict.fromkeys(upi_ids)),
            "phishingLinks": list(dict.fromkeys(phishing_links)),
            "phoneNumbers": list(dict.fromkeys(phone_numbers)),
            "suspiciousKeywords": list(dict.fromkeys(suspicious_keywords)),
        }

    def _calculate_confidence_scores(
        self,
        entities: Dict[str, List[Dict[str, Any]]],
        patterns: Dict[str, List[str]],
    ) -> Dict[str, float]:
        """Calculate confidence scores by category."""
        scores: Dict[str, float] = {}

        # NER confidence averages
        for category, ent_list in entities.items():
            if ent_list:
                scores[category] = sum(e.get("confidence", 0.9) for e in ent_list) / len(ent_list)
            else:
                scores[category] = 0.0

        # Regex-based confidence
        for key in ["phone_numbers", "upi_ids", "urls", "emails", "ifsc_codes"]:
            scores[key] = 0.95 if patterns.get(key) else 0.0
        scores["account_numbers"] = 0.7 if patterns.get("account_numbers") else 0.0

        # Overall score
        non_zero = [v for v in scores.values() if v > 0]
        scores["overall"] = sum(non_zero) / len(non_zero) if non_zero else 0.0

        return scores

    def extract(self, transcript: str) -> Dict[str, Any]:
        """Main extraction method matching ExtractResponse schema."""
        try:
            self._validate_transcript(transcript)

            entities = self._extract_named_entities(transcript)
            patterns = self._extract_regex_patterns(transcript)
            intelligence = self._build_scammer_intelligence(entities, patterns)
            confidence = self._calculate_confidence_scores(entities, patterns)

            combined_entities = {**entities, **patterns}

            return {
                "entities": combined_entities,
                "scammer_intelligence": intelligence,
                "confidence_scores": confidence,
            }

        except (ValueError, FileNotFoundError) as e:
            raise

        except Exception as e:
            self.logger.error(f"Extraction failed: {e}", exc_info=True)
            return {
                "entities": {},
                "scammer_intelligence": {},
                "confidence_scores": {},
            }

    def extract_demo(self, transcript: str, mock_result: bool = False) -> Dict[str, Any]:
        """Demo mode extraction with mock results."""
        if settings.DEMO_MODE and mock_result:
            lower = transcript.lower()
            entities = {
                "PERSON": [{"text": "John Doe", "start": 0, "end": 8, "confidence": 0.9}],
                "ORG": [{"text": "Fake Bank", "start": 10, "end": 19, "confidence": 0.88}],
            }
            patterns = {
                "upi_ids": ["john@paytm"] if "upi" in lower else [],
                "phone_numbers": ["+919876543210"] if "phone" in lower else [],
                "urls": ["https://scam-site.com"] if "http" in lower else [],
                "emails": ["scammer@example.com"] if "email" in lower else [],
                "ifsc_codes": ["SBIN0001234"] if "ifsc" in lower else [],
                "account_numbers": ["123456789012"] if "account" in lower else [],
            }
            intelligence = self._build_scammer_intelligence(entities, patterns)
            confidence = self._calculate_confidence_scores(entities, patterns)
            combined_entities = {**entities, **patterns}

            return {
                "entities": combined_entities,
                "scammer_intelligence": intelligence,
                "confidence_scores": confidence,
            }

        return self.extract(transcript)

    def extract_batch(self, transcripts: List[str]) -> List[Dict[str, Any]]:
        """Batch extraction for multiple transcripts."""
        if not transcripts:
            return []

        # Validate all transcripts first
        for i, t in enumerate(transcripts):
            self._validate_transcript(t)

        # Load model once
        self._load_model()

        results = []
        for i, transcript in enumerate(transcripts):
            try:
                results.append(self.extract(transcript))
            except Exception as e:
                self.logger.error(f"Batch extraction failed for index {i}: {e}")
                results.append({
                    "entities": {},
                    "scammer_intelligence": {},
                    "confidence_scores": {},
                })

        return results


_extractor_instance: Optional[EntityExtractor] = None


def get_entity_extractor() -> EntityExtractor:
    """Get the global EntityExtractor singleton instance."""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = EntityExtractor()
    return _extractor_instance
