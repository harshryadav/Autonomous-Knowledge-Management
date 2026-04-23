from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')

def embed_chunks(chunks):
    texts = [c["content"] for c in chunks]
    embeddings = model.encode(texts)
    return embeddings