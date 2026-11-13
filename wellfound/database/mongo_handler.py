"""
wellfound/database/mongo_handler.py
MongoDB persistence layer for the Wellfound pipeline.
Tracks scraped jobs, applications, extracted emails, and sent emails.
"""

from datetime import datetime, timedelta, timezone
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError


class WellfoundMongoHandler:
    def __init__(self, uri: str, db_name: str,
                 jobs_col: str, applied_col: str,
                 emails_col: str, sent_col: str):
        self.client  = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.db      = self.client[db_name]
        self.jobs    = self.db[jobs_col]
        self.applied = self.db[applied_col]
        self.emails  = self.db[emails_col]
        self.sent    = self.db[sent_col]
        self._ensure_indexes()
        print(f"[WF MongoDB] ✅ Connected to '{db_name}'")

    def _ensure_indexes(self):
        # Jobs: unique by job_id
        self.jobs.create_index([("job_id", ASCENDING)], unique=True, sparse=True)
        # Applied: unique by job_id
        self.applied.create_index([("job_id", ASCENDING)], unique=True, sparse=True)
        # Emails: unique by email address
        self.emails.create_index([("email", ASCENDING)], unique=True, sparse=True)
        # Sent: compound index email + sent_at for cooldown queries
        self.sent.create_index([("email", ASCENDING), ("sent_at", ASCENDING)])

    # ── Jobs ─────────────────────────────────────────────────────
    def save_job(self, job: dict) -> bool:
        """Save scraped job. Returns True if new, False if duplicate."""
        try:
            doc = {**job, "scraped_at": datetime.utcnow()}
            self.jobs.insert_one(doc)
            return True
        except DuplicateKeyError:
            return False
        except Exception as e:
            print(f"[WF MongoDB] save_job error: {e}")
            return False

    def get_jobs_not_applied(self, cooldown_days: int = 30) -> list[dict]:
        """Return jobs not yet successfully applied to, closed, or ineligible."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=cooldown_days)
        applied_ids = set(
            d["job_id"] for d in self.applied.find(
                {
                    "status": {"$in": ["applied", "already_applied", "external_ats", "closed", "ineligible"]},
                    "applied_at": {"$gte": cutoff}
                },
                {"job_id": 1}
            )
        )
        query = {}
        if applied_ids:
            query["job_id"] = {"$nin": list(applied_ids)}
        return list(self.jobs.find(query))

    def clean_false_already_applied(self):
        """Clean up records falsely marked as already_applied due to navbar 'Applied' link."""
        try:
            res = self.applied.delete_many({"status": "already_applied", "message": "Already applied"})
            if res.deleted_count > 0:
                print(f"[WF MongoDB] 🧹 Cleaned {res.deleted_count} false 'already applied' entries for retry")
        except Exception:
            pass

    # ── Applied ──────────────────────────────────────────────────
    def save_application(self, result: dict) -> bool:
        """Record or update a job application result."""
        try:
            doc = {**result, "applied_at": datetime.utcnow()}
            job_id = result.get("job_id")
            if job_id:
                self.applied.update_one({"job_id": job_id}, {"$set": doc}, upsert=True)
            else:
                self.applied.insert_one(doc)
            return True
        except Exception as e:
            print(f"[WF MongoDB] save_application error: {e}")
            return False

    def was_applied(self, job_id: str) -> bool:
        return self.applied.find_one({"job_id": job_id}) is not None

    # ── Emails (from job descriptions) ───────────────────────────
    def save_email(self, record: dict) -> bool:
        """Save extracted recruiter email. Returns True if new."""
        try:
            doc = {**record, "extracted_at": datetime.utcnow(), "status": "pending"}
            self.emails.insert_one(doc)
            return True
        except DuplicateKeyError:
            return False
        except Exception as e:
            print(f"[WF MongoDB] save_email error: {e}")
            return False

    def get_pending_emails(self, cooldown_days: int = 15) -> list[dict]:
        """Return emails not sent in the last cooldown_days."""
        cutoff = datetime.utcnow() - timedelta(days=cooldown_days)
        recently_sent = set(
            d["email"] for d in self.sent.find(
                {"sent_at": {"$gte": cutoff}}, {"email": 1}
            )
        )
        query = {}
        if recently_sent:
            query["email"] = {"$nin": list(recently_sent)}
        return list(self.emails.find(query))

    # ── Sent emails ───────────────────────────────────────────────
    def log_sent_email(self, email: str, subject: str, company: str = ""):
        try:
            self.sent.insert_one({
                "email":   email,
                "subject": subject,
                "company": company,
                "sent_at": datetime.utcnow(),
                "source":  "wellfound",
            })
        except Exception as e:
            print(f"[WF MongoDB] log_sent_email error: {e}")

    # ── Stats ─────────────────────────────────────────────────────
    def stats(self) -> dict:
        return {
            "total_jobs_scraped": self.jobs.count_documents({}),
            "total_applied":      self.applied.count_documents({}),
            "total_emails_found": self.emails.count_documents({}),
            "total_emails_sent":  self.sent.count_documents({}),
        }

    def close(self):
        self.client.close()
