"""
Diagnostic script to check the contents of wf_applied_jobs in MongoDB.
"""
from pymongo import MongoClient
from datetime import datetime, timedelta

client = MongoClient("mongodb://localhost:27017")
db = client["linkedin_scraper"]
col = db["wf_applied_jobs"]

total = col.count_documents({})
applied_ok = col.count_documents({"status": "applied"})
already_applied = col.count_documents({"status": "already_applied"})
external_ats = col.count_documents({"status": "external_ats"})
failed = col.count_documents({"status": "failed"})
closed = col.count_documents({"status": "closed"})

print("=" * 50)
print(f"Total records in wf_applied_jobs: {total}")
print(f"  - status 'applied'        : {applied_ok}")
print(f"  - status 'already_applied': {already_applied}")
print(f"  - status 'external_ats'   : {external_ats}")
print(f"  - status 'failed'         : {failed}")
print(f"  - status 'closed'         : {closed}")
print("=" * 50)

print("\nRecent 10 applications in MongoDB:")
for doc in col.find().sort("applied_at", -1).limit(10):
    t = doc.get("title", "")
    c = doc.get("company", "")
    s = doc.get("status", "")
    m = doc.get("message", "")
    dt = doc.get("applied_at", "")
    print(f"[{s}] {t} @ {c} | msg: {m} | time: {dt}")
