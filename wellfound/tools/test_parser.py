"""Quick offline test — parses the saved next_data.json without browser."""
import json, re, sys
from pathlib import Path

f = Path(__file__).resolve().parent / "debug_output" / "next_data.json"
if not f.exists():
    print(f"Debug file not found at: {f}")
    sys.exit(0)
raw  = f.read_text(encoding="utf-8")
data = json.loads(raw)
apollo = data["props"]["pageProps"]["apolloState"]["data"]

jobs, companies = [], {}
for key, val in apollo.items():
    if key.startswith("StartupResult:"):
        sid = key.split(":",1)[1]
        companies[sid] = {
            "name": val.get("name",""),
            "job_refs": [r.get("__ref","") for r in val.get("highlightedJobListings",[])]
        }

job_to_co = {}
for sid, ci in companies.items():
    for ref in ci["job_refs"]:
        job_to_co[ref] = ci

for key, val in apollo.items():
    if not key.startswith("JobListingSearchResult:"): continue
    jid   = str(val.get("id", key.split(":",1)[1]))
    slug  = val.get("slug","")
    title = val.get("title","")
    desc  = val.get("description","") or ""
    emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", desc)
    cinfo = job_to_co.get(key,{})
    jobs.append({
        "id": jid, "title": title,
        "company": cinfo.get("name",""),
        "min_exp": val.get("yearsExperienceMin") or 0,
        "max_exp": val.get("yearsExperienceMax") or 99,
        "url": f"https://wellfound.com/jobs/{jid}-{slug}",
        "emails": emails,
    })

print(f"Jobs found in page 1 cache: {len(jobs)}")
for j in jobs[:8]:
    print(f"  [{j['id']}] {j['title']} @ {j['company']}  exp:{j['min_exp']}-{j['max_exp']}y  emails:{j['emails']}")
