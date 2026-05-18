import os
from dotenv import load_dotenv
load_dotenv()

import chromadb
from chromadb.utils import embedding_functions

ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=os.getenv("OPENAI_API_KEY"),
    model_name="text-embedding-3-small"
)

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_collection(name="kam_schema_store", embedding_function=ef)

# Test 1 — Business glossary terms
print("=" * 50)
print("GLOSSARY TERMS TEST")
print("=" * 50)
glossary_queries = [
    "What is inbound?",
    "What is a gross rate?",
    "What does commissionable mean?",
    "What is a net rate?",
    "What is domestic US?",
]
for q in glossary_queries:
    r = collection.query(query_texts=[q], n_results=1)
    doc_id = r["ids"][0][0]
    snippet = r["documents"][0][0][:80].strip().replace("\n", " ")
    print(f"  ✓ '{q}' → {doc_id}")
    print(f"    {snippet}...")

# Test 2 — Schema/table/column questions
print("\n" + "=" * 50)
print("SCHEMA QUESTIONS TEST")
print("=" * 50)
schema_queries = [
    "Which table contains rate codes?",
    "What columns does the product table have?",
    "What is the supplier_id column?",
    "How do I join supplier to client_supplier?",
    "What is the client_name column in the product table?",
]
for q in schema_queries:
    r = collection.query(query_texts=[q], n_results=1)
    doc_id = r["ids"][0][0]
    snippet = r["documents"][0][0][:80].strip().replace("\n", " ")
    print(f"  ✓ '{q}' → {doc_id}")
    print(f"    {snippet}...")