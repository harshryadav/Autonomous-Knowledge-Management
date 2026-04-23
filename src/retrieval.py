import faiss
import numpy as np

class Retriever:
    def __init__(self, dim=384):
        self.index = faiss.IndexFlatL2(dim)
        self.chunks = []

    def add(self, embeddings, chunks):
        self.index.add(np.array(embeddings))
        self.chunks = chunks

    def search(self, query_embedding, k=5):
        D, I = self.index.search(query_embedding, k)
        return [self.chunks[i] for i in I[0]]