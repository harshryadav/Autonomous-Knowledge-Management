from src.ingestion import load_repo
from src.chunking import chunk_documents
from src.embeddings import embed_chunks, model
from src.retrieval import Retriever

repo_path = "data/repo1"

# Step 1: Load
docs = load_repo(repo_path)

# Step 2: Chunk
chunks = chunk_documents(docs)

# Step 3: Embed
embeddings = embed_chunks(chunks)

# Step 4: Store
retriever = Retriever()
retriever.add(embeddings, chunks)

print("Pipeline ready!")