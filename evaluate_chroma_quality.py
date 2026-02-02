# evaluate_chroma_quality.py
import os
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_openai import AzureOpenAIEmbeddings

load_dotenv()

# -------------------- ENV --------------------
PERSIST_DIR = "./chroma_db_chunk_600_overlap_100"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

# -------------------- Embeddings --------------------
embeddings = AzureOpenAIEmbeddings(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    azure_deployment=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    openai_api_key=OPENAI_API_KEY,
)

# -------------------- Load DB --------------------
db = Chroma(
    persist_directory=PERSIST_DIR,
    embedding_function=embeddings
)

# -------------------- 1️⃣ DB HEALTH --------------------
print("\n=== DATABASE HEALTH ===")
print("Total chunks:", db._collection.count())

# -------------------- 2️⃣ TEST QUERIES --------------------
evaluation_queries = [
    {
        "query": "What is Net Present Value?",
        "expected_keywords": ["present value", "cash flows"]
    },
    {
        "query": "Define Internal Rate of Return",
        "expected_keywords": ["discount rate", "net present value"]
    },
    {
        "query": "What is EBITDA?",
        "expected_keywords": ["earnings", "interest", "tax"]
    }
]

# -------------------- 3️⃣ EVALUATION --------------------
k = 5
successful_hits = 0
total_queries = len(evaluation_queries)
metadata_coverage = []

print("\n=== RETRIEVAL QUALITY ===")

for test in evaluation_queries:
    query = test["query"]
    keywords = test["expected_keywords"]

    docs = db.similarity_search_with_score(query, k=k)

    print(f"\nQuery: {query}")

    hit = False
    for rank, (doc, score) in enumerate(docs, start=1):
        content = doc.page_content.lower()
        meta = doc.metadata

        print(f"  Rank {rank} | Score: {score:.4f}")
        print(f"    Source: {meta.get('source')} | Page: {meta.get('page')}")

        if all(word in content for word in keywords):
            hit = True

        metadata_coverage.append(
            all(key in meta for key in ["source", "page", "chunk_id"])
        )

    if hit:
        successful_hits += 1

# -------------------- 4️⃣ METRICS --------------------
recall_at_k = successful_hits / total_queries
metadata_score = sum(metadata_coverage) / len(metadata_coverage)

print("\n=== FINAL METRICS ===")
print(f"Recall@{k}: {recall_at_k:.2f}")
print(f"Metadata completeness: {metadata_score:.2f}")

# -------------------- 5️⃣ INTERPRETATION --------------------
print("\n=== INTERPRETATION ===")

if recall_at_k >= 0.8:
    print("✔ High retrieval quality")
elif recall_at_k >= 0.6:
    print("⚠ Medium retrieval quality")
else:
    print("✘ Low retrieval quality")

if metadata_score >= 0.9:
    print("✔ Metadata quality is excellent")
else:
    print("⚠ Metadata quality needs improvement")
