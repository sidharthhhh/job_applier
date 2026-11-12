"""
database/mongo_handler.py
Handles all MongoDB operations for the LinkedIn Scraper pipeline
"""

from datetime import datetime, timedelta
import hashlib
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, OperationFailure
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config


class MongoHandler:
    def __init__(self):
        self.client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
        self.client.admin.command("ping")
        self.db = self.client[Config.MONGO_DB]

        # Collections
        self.posts = self.db[Config.MONGO_POSTS_COLLECTION]
        self.emails = self.db[Config.MONGO_EMAILS_COLLECTION]
        self.sent = self.db[Config.MONGO_SENT_COLLECTION]
        self.responses = self.db[Config.MONGO_RESPONSES_COLLECTION]

        self._create_indexes()
        print(f"[MongoDB] ✅ Connected to '{Config.MONGO_DB}'")

    def _create_indexes(self):
        """Create indexes for faster queries and uniqueness"""
        # Unique email in extracted_emails
        self.emails.create_index([("email", ASCENDING)], unique=True)
        # Index on sent_at for cooldown and daily quota queries
        self.sent.create_index([("email", ASCENDING), ("sent_at", DESCENDING)])
        self.sent.create_index([("sent_at", DESCENDING)])

        # Partial unique index on non-empty post_url so posts lacking URLs don't collide on ""
        try:
            existing = self.posts.index_information()
            if "post_url_1" in existing and "partialFilterExpression" not in existing["post_url_1"]:
                self.posts.drop_index("post_url_1")
            self.posts.create_index(
                [("post_url", ASCENDING)],
                unique=True,
                partialFilterExpression={"post_url": {"$type": "string", "$gt": ""}},
            )
        except OperationFailure:
            self.posts.create_index([("post_url", ASCENDING)])

        self.posts.create_index(
            [("content_hash", ASCENDING)],
            unique=True,
            partialFilterExpression={"content_hash": {"$type": "string", "$gt": ""}},
        )

    # ─── POSTS ──────────────────────────────────────────────
    def save_post(self, post: dict) -> bool:
        """Save scraped LinkedIn post. Returns True if new, False if duplicate."""
        doc = dict(post)
        doc["scraped_at"] = datetime.utcnow()
        text_sample = (doc.get("post_text") or "").strip()[:250].lower()
        if text_sample:
            doc["content_hash"] = hashlib.sha256(text_sample.encode("utf-8")).hexdigest()
        try:
            self.posts.insert_one(doc)
            return True
        except DuplicateKeyError:
            return False

    def get_all_posts(self) -> list:
        """Get all scraped posts"""
        return list(self.posts.find({}, {"_id": 0}))

    # ─── EMAILS ─────────────────────────────────────────────
    def save_email(self, email_data: dict) -> bool:
        """Save extracted email. Returns True if new, False if already exists."""
        doc = dict(email_data)
        doc["email"] = doc["email"].lower().strip()
        doc["extracted_at"] = datetime.utcnow()
        if "status" not in doc:
            doc["status"] = "pending"
        try:
            self.emails.insert_one(doc)
            return True
        except DuplicateKeyError:
            return False

    def is_email_on_cooldown(self, email: str) -> bool:
        """
        Check if we already mailed this address within EMAIL_COOLDOWN_DAYS.
        Returns True if on cooldown (skip), False if safe to send.
        """
        cutoff = datetime.utcnow() - timedelta(days=Config.EMAIL_COOLDOWN_DAYS)
        record = self.sent.find_one({
            "email": email.lower().strip(),
            "sent_at": {"$gte": cutoff}
        })
        return record is not None

    def mark_email_invalid(self, email: str, reason: str = "invalid_mx"):
        """Mark an email as invalid in extracted_emails so it's not picked up again"""
        self.emails.update_one(
            {"email": email.lower().strip()},
            {"$set": {"status": "invalid", "invalid_reason": reason, "updated_at": datetime.utcnow()}}
        )

    def get_pending_emails(self, only_emails: set[str] | None = None) -> list:
        """
        Get unsent pending emails, excluding already sent/invalid/bounced/replied ones.
        If only_emails is provided, restrict strictly to those newly scraped addresses.
        """
        query: dict = {"status": "pending"}
        if only_emails is not None:
            normalized = [e.lower().strip() for e in only_emails if e]
            if not normalized:
                return []
            query["email"] = {"$in": normalized}

        all_emails = list(self.emails.find(query, {"_id": 0}))
        if not all_emails:
            return []

        cutoff = datetime.utcnow() - timedelta(days=Config.EMAIL_COOLDOWN_DAYS)
        cooled_down = {
            e.lower().strip()
            for e in self.sent.distinct("email", {"sent_at": {"$gte": cutoff}})
            if isinstance(e, str)
        }
        return [e for e in all_emails if e.get("email", "").lower().strip() not in cooled_down]

    def get_sent_count_today(self) -> int:
        """Count emails sent since start of current UTC day."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.sent.count_documents({"sent_at": {"$gte": today}})

    # ─── SENT EMAILS ────────────────────────────────────────
    def log_sent_email(self, email: str, subject: str, body: str,
                       post_url: str, company: str = "") -> str:
        """Log a successfully sent email into sent_emails and update extracted_emails."""
        norm_email = email.lower().strip()
        now = datetime.utcnow()
        doc = {
            "email": norm_email,
            "subject": subject,
            "body": body,
            "post_url": post_url,
            "company": company,
            "sent_at": now,
            "status": "sent",       # sent / replied / bounced
            "reply_received": False
        }
        result = self.sent.insert_one(doc)

        # Also update extracted_emails collection
        self.emails.update_one(
            {"email": norm_email},
            {"$set": {"status": "sent", "last_sent_at": now}}
        )
        return str(result.inserted_id)

    def update_email_status(self, email: str, status: str):
        """Update status on the latest sent_emails entry and extracted_emails"""
        norm_email = email.lower().strip()
        now = datetime.utcnow()
        self.sent.find_one_and_update(
            {"email": norm_email},
            {"$set": {"status": status, "updated_at": now}},
            sort=[("sent_at", DESCENDING)],
        )
        self.emails.update_one(
            {"email": norm_email},
            {"$set": {"status": status, "updated_at": now}}
        )

    # ─── RESPONSES ──────────────────────────────────────────
    def save_response(self, email: str, reply_body: str, sentiment: str = "unknown"):
        """Log a reply received for a sent email"""
        doc = {
            "email": email.lower().strip(),
            "reply_body": reply_body,
            "sentiment": sentiment,   # positive / negative / neutral
            "received_at": datetime.utcnow()
        }
        self.responses.insert_one(doc)
        # Also update sent email status
        self.update_email_status(email, "replied")

    # ─── STATS ──────────────────────────────────────────────
    def get_stats(self) -> dict:
        """Return overall stats for display"""
        total_sent = self.sent.count_documents({})
        replied = self.sent.count_documents({"status": "replied"})
        bounced = self.sent.count_documents({"status": "bounced"})
        today = datetime.utcnow().replace(hour=0, minute=0, second=0)
        sent_today = self.sent.count_documents({"sent_at": {"$gte": today}})

        return {
            "total_posts_scraped": self.posts.count_documents({}),
            "total_emails_extracted": self.emails.count_documents({}),
            "total_sent": total_sent,
            "sent_today": sent_today,
            "replied": replied,
            "bounced": bounced,
            "reply_rate": f"{(replied/total_sent*100):.1f}%" if total_sent > 0 else "0%"
        }

    def close(self):
        self.client.close()
