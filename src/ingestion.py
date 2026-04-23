def load_repo(repo_path):
    documents = []

    # Load README
    try:
        with open(f"{repo_path}/README.md", "r") as f:
            documents.append({
                "type": "readme",
                "content": f.read(),
                "file": "README.md"
            })
    except:
        pass

    # Load code files (simple version)
    import os
    for file in os.listdir(repo_path):
        if file.endswith(".py"):
            with open(f"{repo_path}/{file}", "r") as f:
                documents.append({
                    "type": "code",
                    "content": f.read(),
                    "file": file
                })

    return documents