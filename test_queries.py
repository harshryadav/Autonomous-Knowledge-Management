from src.embeddings import model
from main import retriever

def test_query(q):
    q_emb = model.encode([q])
    results = retriever.search(q_emb, k=5)

    print(f"\nQuery: {q}")
    for r in results:
        print("----")
        print(f"[{r['type']}] {r['file']}")
        print(r["content"][:200])

queries = [
    "What does this repo do?",
    "Where is caching used?",
    "What functions are defined?"
]

for q in queries:
    test_query(q)