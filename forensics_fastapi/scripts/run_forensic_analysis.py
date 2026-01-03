import json

import psycopg2
from src.config import DB_CONFIG, RAG_NAME
from src.core.worker_ai import WorkerAI

# Configuration
CLOUDFLARE_RAG_NAME = RAG_NAME


def get_db_conn():
    return psycopg2.connect(**DB_CONFIG)


def perform_local_vector_search(ai, conn, query, limit=5):
    """
    Performs vector search against local 'messages' and 'threads' tables.
    """


    # We search both tables.
    # worker_ai.search_sql generates the SQL, but we need to execute it.

    # 1. Generate SQL for 'messages'
    sql_messages = ai.search_sql(query, "messages", limit=limit)
    if sql_messages:
        with conn.cursor() as cur:
            # We need to modify the SQL slightly to select more fields if needed,
            # but search_sql returns a fixed string.
            # Actually search_sql returns "SELECT id, subject, ...".
            # Let's inspect worker_ai.py again.
            # It selects: id, subject, 1 - (embedding <=> vector)
            # We probably want 'bodyplain' too for context.
            # Since search_sql is hardcoded, we might need to query manually using generate_embeddings directly
            # OR just update worker_ai.py to be more flexible.
            # For now, let's use the embedding generation helper and write our own SQL here for flexibility.
            pass

    # Better approach: Manually generate embedding and query here to get proper fields.
    vectors = ai.generate_embeddings([query])
    if not vectors:
        return []

    vector_str = str(vectors[0])

    with conn.cursor() as cur:
        # Search Messages
        cur.execute(f"""
            SELECT 'message' as type, id, subject, bodyplain, sentdate as date, 1 - (embedding <=> '{vector_str}') as similarity
            FROM messages
            ORDER BY embedding <=> '{vector_str}'
            LIMIT {limit}
        """)
        msg_rows = cur.fetchall()

        # Search Threads
        cur.execute(f"""
            SELECT 'thread' as type, id, subject, 'No Body' as bodyplain, NULL as date, 1 - (embedding <=> '{vector_str}') as similarity
            FROM threads
            ORDER BY embedding <=> '{vector_str}'
            LIMIT {limit}
        """)
        thread_rows = cur.fetchall()

    # Combine and sort
    all_rows = msg_rows + thread_rows
    # Sort by similarity desc
    all_rows.sort(key=lambda x: x[5], reverse=True)

    formatted_results = []
    for row in all_rows[:limit]:  # Take top N overall
        formatted_results.append(
            f"[{row[0].upper()}] Date: {row[4] or 'N/A'} | Subject: {row[2]} | Snippet: {row[3][:200]}..."
        )

    return formatted_results


def analyze_question(ai, conn, question_obj):
    query = question_obj["query"]
    category = question_obj["category"]
    print(f"\nAnalyzing: {query} ({category})")

    # 1. AutoRAG Search (Cloudflare)
    print(" - Searching AutoRAG...")
    rag_response = ai.rag_search_only(CLOUDFLARE_RAG_NAME, query, max_results=5)
    rag_context = []
    if rag_response and "results" in rag_response:
        for r in rag_response["results"]:
            rag_context.append(f"[AutoRAG] {r.get('text', '')[:300]}...")

    # 2. Local Vector Search (Postgres)
    print(" - Searching Local DB...")
    local_context = perform_local_vector_search(ai, conn, query, limit=5)

    combined_context = "\n".join(rag_context + local_context)

    # 3. Structured Reasoning
    print(" - Running Forensic Reasoning...")

    # Define Schema for CSLB/Forensic Report
    schema = {
        "type": "object",
        "properties": {
            "finding_summary": {
                "type": "string",
                "description": "A comprehensive, forensic summary of the findings regarding this question.",
            },
            "key_dates": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of specific dates mentioned in evidence related to this issue.",
            },
            "contradictions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of contradictions or inconsistencies found in the provider's narrative.",
            },
            "evidence_strength": {
                "type": "string",
                "enum": ["Strong", "Moderate", "Weak", "Inconclusive"],
                "description": "Assessment of the evidence strength.",
            },
            "missing_information": {
                "type": "string",
                "description": "Critical information that is missing or not addressed.",
            },
        },
        "required": ["finding_summary", "evidence_strength"],
    }

    prompt = f"""
    You are a forensic investigator analyzing a construction dispute.
    
    QUESTION: {query}
    CONTEXT (Evidence from emails/docs):
    {combined_context}
    
    Analyze the context to answer the question. 
    Focus on factual consistency, dates, and contradictions.
    If the evidence is thin, state that.
    """

    result = ai.run_structured_reasoning(prompt, json_schema=schema)

    return {"question": query, "category": category, "analysis": result}


def generate_markdown_report(analysis_results):
    md = "# Forensic Analysis Report: Mr. Roofing Dispute\n\n"
    md += "Generated by AI Forensic System\n\n"

    current_cat = None

    for item in analysis_results:
        if item["category"] != current_cat:
            current_cat = item["category"]
            md += f"## {current_cat}\n\n"

        q = item["question"]
        a = item["analysis"]

        if not a:
            md += f"### Q: {q}\n*Analysis Failed*\n\n"
            continue

        md += f"### Q: {q}\n"
        md += f"**Finding:** {a.get('finding_summary', 'No summary provided')}\n\n"

        if a.get("key_dates"):
            md += "**Key Dates:** " + ", ".join(a["key_dates"]) + "\n\n"

        if a.get("contradictions"):
            md += "**Contradictions Identified:**\n"
            for c in a["contradictions"]:
                md += f"- {c}\n"
            md += "\n"

        md += f"**Evidence Strength:** {a.get('evidence_strength', 'N/A')}\n\n"

        if a.get("missing_information"):
            md += f"*Gap Analysis:* {a['missing_information']}\n\n"

        md += "---\n\n"

    return md


def main():
    ai = WorkerAI()
    try:
        conn = get_db_conn()
        print("Connected to DB.")
    except Exception as e:
        print(f"DB Connection Failed: {e}")
        return

    # Create Table if not exists
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS forensic_findings (
                id SERIAL PRIMARY KEY,
                question TEXT,
                category TEXT,
                finding_summary TEXT,
                analysis_json JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        conn.commit()

    # Load Questions
    with open("questions.json", "r") as f:
        questions = json.load(f)

    results = []

    total = len(questions)
    print(f"Starting analysis of {total} forensic questions...")

    for i, q in enumerate(questions):
        print(f"[{i + 1}/{total}] Processing...")
        res = analyze_question(ai, conn, q)
        results.append(res)

        # Save to DB
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO forensic_findings (question, category, finding_summary, analysis_json) "
                    "VALUES (%s, %s, %s, %s)",
                    (
                        res["question"],
                        res["category"],
                        res["analysis"].get("finding_summary", ""),
                        json.dumps(res["analysis"]),
                    ),
                )
                conn.commit()
        except Exception as e:
            print(f"Failed to save finding to DB: {e}")
            conn.rollback()

        # Save incremental results to file
        if (i + 1) % 5 == 0:
            with open("forensic_results_temp.json", "w") as f:
                json.dump(results, f, indent=2)

    conn.close()

    # Save Final JSON
    with open("forensic_report.json", "w") as f:
        json.dump(results, f, indent=2)

    print(
        "Forensic Search & Analysis Complete. Logic for final report generation to be triggered separately."
    )
    # Note: We can import generate_reports here if we want immediate generation,
    # but the user asked for "another python module" to create info.
    # For now, let's keep this focused on the search/save.


if __name__ == "__main__":
    main()
