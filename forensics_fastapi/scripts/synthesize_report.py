import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import text
from src.config import CLIENT_INFO, CONTRACTOR_INFO, DB_CONFIG, RAG_NAME
from src.core.database import get_engine
from src.core.worker_ai import WorkerAI
from src.reports.generate_reports import (
    schema_cslb_report,
    schema_exhibit_labels,
    schema_timeline_contradictions,
)


def fetch_table_data(engine, table_name: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """Generic fetcher for raw tables."""
    try:
        sql = text(f"SELECT * FROM {table_name} LIMIT {limit}")
        with engine.connect() as conn:
            result = conn.execute(sql)
            return [dict(row._mapping) for row in result]
    except Exception as e:
        print(f"Warning: Could not fetch {table_name}: {e}")
        return []


def fetch_all_findings(engine) -> List[Dict[str, Any]]:
    """
    Retrieves all forensic findings from the database.
    Returns a list of dicts: {question, category, finding_summary, analysis_json}
    """
    sql = text("""
        SELECT question, category, finding_summary, analysis_json
        FROM forensic_findings
        ORDER BY id ASC
    """)

    with engine.connect() as conn:
        result = conn.execute(sql)
        rows = result.fetchall()

    findings = []
    for r in rows:
        findings.append(
            {
                "question": r[0],
                "category": r[1],
                "finding_summary": r[2],
                "analysis": r[3] if isinstance(r[3], dict) else json.loads(r[3] if r[3] else "{}"),
            }
        )
    return findings


def get_dispute_date(engine) -> str:
    """
    Finds the date of the last email from 'Mark' (approximate dispute date).
    Falls back to current date if not found.
    """
    sql = text("""
        SELECT sentdate
        FROM messages
        WHERE fromaddress ILIKE '%Mark%' OR bodyplain ILIKE '%Mark%'
        ORDER BY sentdate DESC
        LIMIT 1
    """)
    try:
        with engine.connect() as conn:
            result = conn.execute(sql).fetchone()
            if result and result[0]:
                val = result[0]
                # If it's already a datetime object
                if hasattr(val, "strftime"):
                    return val.strftime("%B %d, %Y")
                # If it's a string, try to parse or return as is
                try:
                    # simplistic parse attempt if it's ISOish
                    dt = pd.to_datetime(val)
                    return dt.strftime("%B %d, %Y")
                except Exception:
                    return str(val)
    except Exception as e:
        print(f"Warning: Could not determine dispute date: {e}")

    return datetime.now().strftime("%B %d, %Y")


def synthesize_timeline(
    ai: WorkerAI, findings: List[Dict[str, Any]], rolodex: List[Dict]
) -> Dict[str, Any]:
    print("Synthesizing Master Timeline...")

    # Create Rolodex Context
    rolodex_str = "\n".join(
        [f"{r.get('name')} ({r.get('email')}) - {r.get('type')}" for r in rolodex[:50]]
    )

    # Aggregate all key dates and events from individual findings
    events_blob = []
    for f in findings:
        q = f.get("question", "")
        cat = f.get("category", "")
        ana = f.get("analysis", {})
        summary = ana.get("finding_summary", "")
        dates = ana.get("key_dates", [])

        if summary or dates:
            events_blob.append(f"Category: {cat}\nContext: {q}\nFinding: {summary}\nDates: {dates}")

    context_text = "\n---\n".join(events_blob)

    prompt = f"""
    You are the Chief Forensic Analyst.
    Synthesize a SINGLE master timeline and contradiction dictionary.
    
    KEY ACTORS (Rolodex):
    {rolodex_str}

    Source Findings:
    {context_text[:100000]} 
    
    Output strictly matching the JSON schema for timeline and contradictions.
    Use the Rolodex to normalize names in the 'actors' or 'party' fields.
    """

    return ai.run_structured_llama(
        prompt=prompt,
        json_schema=schema_timeline_contradictions(),
        system_prompt="You are an expert synthesizer. Merge duplicate events. Resolve conflicts where possible or flag them.",
    )


def synthesize_cslb_report(
    ai: WorkerAI, findings: List[Dict[str, Any]], timeline_data: Dict[str, Any]
) -> Dict[str, Any]:
    print("Synthesizing CSLB Narrative...")

    # We can use the timeline we just generated + high level summaries
    timeline_str = json.dumps(timeline_data.get("timeline", [])[:20], indent=2)  # Top 20 events
    contradictions_str = json.dumps(timeline_data.get("contradictions", []), indent=2)

    # Collect category summaries
    cat_summaries = {}
    for f in findings:
        cat = f["category"]
        if cat not in cat_summaries:
            cat_summaries[cat] = []
        cat_summaries[cat].append(f.get("finding_summary", ""))

    cat_text = ""
    for c, sums in cat_summaries.items():
        cat_text += f"## {c}\n" + " ".join(sums[:3]) + "\n"  # Take top 3 summaries per cat

    prompt = f"""
    Draft the Final CSLB Report JSON.
    Use this consolidated information:
    
    TIMELINE HIGHLIGHTS:
    {timeline_str}
    
    CONTRADICTIONS:
    {contradictions_str}
    
    DETAILED FINDINGS BY CATEGORY:
    {cat_text}
    """

    return ai.run_structured_llama(
        prompt=prompt,
        json_schema=schema_cslb_report(),
        system_prompt="Draft a professional, objective CSLB report.",
    )


def synthesize_exhibits(
    ai: WorkerAI,
    findings: List[Dict[str, Any]],
    timeline_data: Dict[str, Any],
    attachments: List[Dict],
) -> Dict[str, Any]:
    print("Synthesizing Exhibit Labels...")

    # Evidence Context
    att_str = "\n".join(
        [f"File: {a.get('filename')} (ID: {a.get('id')})" for a in attachments[:50]]
    )

    # We need to map findings/timeline events to potential exhibits
    timeline_str = json.dumps(timeline_data.get("timeline", [])[:30], indent=2)

    prompt = f"""
    Create a list of Exhibits based on the provided timeline and evidence references.
    Each exhibit should represent a key document or evidence cluster referenced in the timeline.
    
    AVAILABLE EVIDENCE FILES (Assignments):
    {att_str}

    TIMELINE DATA:
    {timeline_str}
    
    Output a JSON matching the exhibit labels schema.
    If an exhibit corresponds to a known file, reference its Filename/ID.
    """

    return ai.run_structured_llama(
        prompt=prompt,
        json_schema=schema_exhibit_labels(),
        system_prompt="You are a forensic clerk. Organize the evidence into clear Exhibits (A, B, C...).",
    )


def main():
    start_time = datetime.now()
    engine = get_engine(DB_CONFIG)
    ai = WorkerAI()

    print("Fetching findings from DB...")
    findings = fetch_all_findings(engine)

    print("Fetching raw evidence contexts (Rolodex, Attachments)...")
    rolodex = fetch_table_data(engine, "rolodex")
    attachments = fetch_table_data(engine, "attachments")
    print(f"Loaded {len(rolodex)} people and {len(attachments)} attachments.")

    if not findings:
        print("No findings found in DB. Run 'run_forensic_analysis.py' first.")
        return

    print(f"Loaded {len(findings)} findings.")

    # 1. Synthesize Timeline
    timeline_data = synthesize_timeline(ai, findings, rolodex)

    # 2. Synthesize CSLB Report
    cslb_data = synthesize_cslb_report(ai, findings, timeline_data)

    # 3. Synthesize Exhibits
    exhibits_data = synthesize_exhibits(ai, findings, timeline_data, attachments)

    # 4. Generate HTML
    # We need to construct the 'bundle' expected by Jinja templates
    # matching generates_reports.py structure
    bundle = {
        "generated_at": datetime.now().isoformat(),
        "rag_name": RAG_NAME,
        "structured": {
            "timeline_matrix": timeline_data,
            "cslb_report": cslb_data,
            "exhibits": exhibits_data,
        },
        "autorag": {},  # not used in logic flow here but template might check
        "queries": {},
    }

    # Save debug bundle
    # --- 5) Save bundle JSON
    # Unwrap 'response' key if present (Cloudflare/Model artifact)
    def unwrap(obj):
        if isinstance(obj, dict) and "response" in obj and len(obj) == 1:
            return obj["response"]
        return obj

    bundle["structured"]["timeline_matrix"] = unwrap(bundle["structured"].get("timeline_matrix"))
    bundle["structured"]["cslb_report"] = unwrap(bundle["structured"].get("cslb_report"))
    bundle["structured"]["exhibits"] = unwrap(bundle["structured"].get("exhibits"))

    # --- 6) Render HTML templates
    BASE_DIR = Path(__file__).resolve().parent.parent / "reports"
    TEMPLATES_DIR = BASE_DIR / "templates"
    OUTPUT_DIR = BASE_DIR / "output_final"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Update bundle path to match new output dir if desired, or keep logic separate.
    # For now, let's keep bundle logic but move the write location or just write it again.

    # Re-save bundle in the correct output dir
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bundle_path = OUTPUT_DIR / f"bundle_{stamp}.json"
    with open(bundle_path, "w") as f:
        json.dump(bundle, f, indent=2)
    print(f"[ok] wrote bundle: {bundle_path}")

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape(["html", "xml"])
    )

    # Case Metadata for Report Header
    dispute_date_str = get_dispute_date(engine)
    case_meta = {
        "case_name": "Mr. Roofing Dispute",
        "client_name": CLIENT_INFO["names"],
        "property_address": CLIENT_INFO["property_address"],
        "contractor_name": CONTRACTOR_INFO["name"],
        "contractor_license": f"{CONTRACTOR_INFO['license_number']} ({CONTRACTOR_INFO['license_status']})",
        "jurisdiction": "CSLB / California",
        "dispute_date": dispute_date_str,
    }

    # Extract questions from findings for the 'queries' context
    questions = [{"question": f["question"], "category": f["category"]} for f in findings]

    render_ctx = {
        "meta": {
            "generated_at": bundle["generated_at"],
            "rag_name": RAG_NAME,
            "bundle_file": bundle_path.name,
        },
        "case": case_meta,
        "queries": questions,
        "autorag": bundle["autorag"],
        "structured": bundle["structured"],
        # Alias for templates expecting 'narrative' or 'timeline' at top level if needed,
        # but templates seem to use 'structured.cslb_report' or 'narrative' variable?
        # cslb_report.html uses 'narrative' variable in loops e.g. narrative.findings_summary
        "narrative": bundle["structured"].get("cslb_report", {}),
        "timeline": [
            {
                **t,
                "reliability_score": int(t.get("confidence", 0) * 10),
                "claim_or_action": t.get("event"),
                "document_refs": t.get("source_refs", []),
                "party": t.get("actors", ["Unknown"])[0] if t.get("actors") else "Unknown",
            }
            for t in bundle["structured"].get("timeline_matrix", {}).get("timeline", [])
        ],
        "contradiction_matrix": {"rows": []},  # Transform for matrix template if needed
        "exhibits": bundle["structured"].get("exhibits", {}).get("exhibits", []),
    }

    # Transform contradictions for specific template format if differing
    # The template expects 'contradiction_matrix.rows'
    # Our schema produces 'contradictions' list.
    # Let's map it.
    raw_contras = bundle["structured"].get("timeline_matrix", {}).get("contradictions", [])
    # Group by topic
    topics = {}
    for c in raw_contras:
        t = c.get("topic", "General")
        if t not in topics:
            topics[t] = []
        topics[t].append(
            {
                "date": "Various",
                "party": "Mixed",
                "statement": f"{c.get('statement_a')} vs {c.get('statement_b')}",
                "doc_ref": str(c.get("statement_a_refs", []))[:20] + "...",
                "stance": "Conflict",
                "contradiction_flag": True,
                "notes": c.get("why_it_conflicts"),
            }
        )

    matrix_rows = []
    for t, entries in topics.items():
        matrix_rows.append({"topic": t, "entries": entries})

    render_ctx["contradiction_matrix"]["rows"] = matrix_rows

    def render(template_name: str, out_name: str):
        try:
            tpl = env.get_template(template_name)
            html = tpl.render(**render_ctx)
            out_path = OUTPUT_DIR / out_name
            out_path.write_text(html, encoding="utf-8")
            print(f"[ok] wrote html: {out_path}")
            return out_path
        except Exception as e:
            print(f"Failed to render {template_name}: {e}")
            return None

    path1 = render("cslb_report.html", "Final_CSLB_Report.html")
    path2 = render("timeline_matrix.html", "Final_Timeline.html")
    # render("exhibit_labels.html", "Final_Exhibits.html")

    print(f"Synthesis Complete in {datetime.now() - start_time}")

    # Open in Chrome
    import subprocess

    try:
        print("Opening reports in Chrome...")
        if path1:
            subprocess.run(["open", "-a", "Google Chrome", str(path1)])
        if path2:
            subprocess.run(["open", "-a", "Google Chrome", str(path2)])
    except Exception as e:
        print(f"Could not open browser: {e}")


if __name__ == "__main__":
    main()
