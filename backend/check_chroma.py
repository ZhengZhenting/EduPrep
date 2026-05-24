import chromadb

client = chromadb.PersistentClient(path="./chroma_db")
collections = client.list_collections()
print("ChromaDB collections:")
for c in collections:
    print(f"  - {c.name}")