def chunk_documents(documents, chunk_size=150):
    chunks = []

    for doc in documents:
        words = doc["content"].split()

        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i+chunk_size])

            chunks.append({
                "content": chunk,
                "type": doc["type"],
                "file": doc["file"]
            })

    return chunks