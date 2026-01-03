import json
import sys

from src.config import RAG_NAME
from src.core.worker_ai import WorkerAI


def main() -> None:
    ai = WorkerAI()

    questions_file = "questions.json"
    if len(sys.argv) > 1 and sys.argv[1].endswith(".json"):
        questions_file = sys.argv[1]

    print(f"Loading questions from {questions_file}...")
    try:
        with open(questions_file, "r") as f:
            questions = json.load(f)
    except FileNotFoundError:
        print(f"Error: {questions_file} not found. Please create it or pass a valid file.")
        sys.exit(1)

    results = {"ai_search": [], "regular_search": []}

    # 1) AI Search
    if "ai_search" in questions:
        qs = questions["ai_search"]
        print(f"\n=== Processing {len(qs)} AI Search queries ===")
        for q in qs:
            print(f"Query: {q}")
            query_text = q["query"] if isinstance(q, dict) and "query" in q else str(q)

            resp = ai.rag_search(RAG_NAME, query_text)

            if resp:
                results["ai_search"].append({"original_query": q, "response": resp})
            else:
                results["ai_search"].append(
                    {"original_query": q, "error": "Failed to get response"}
                )

    # 2) Standard Search
    if "standard_search" in questions:
        qs = questions["standard_search"]
        print(f"\n=== Processing {len(qs)} Standard Search queries ===")
        for q in qs:
            print(f"Query: {q}")
            query_text = q["query"] if isinstance(q, dict) and "query" in q else str(q)

            resp = ai.rag_search_only(RAG_NAME, query_text)

            if resp:
                results["regular_search"].append({"original_query": q, "response": resp})
            else:
                results["regular_search"].append(
                    {"original_query": q, "error": "Failed to get response"}
                )

    # Save results
    output_file = "results.json"
    print(f"\nSaving results to {output_file}...")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print("Done.")


if __name__ == "__main__":
    main()
