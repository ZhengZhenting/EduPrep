from database import SessionLocal
from models import Concept
from rag import get_embedding_function

db = SessionLocal()
emb = get_embedding_function()
todo = db.query(Concept).filter(Concept.embedding.is_(None)).all()
for c in todo:
    text = f"{c.name}: {c.description}" if c.description else c.name
    c.embedding = emb.embed_query(text)
db.commit()
print(f"backfilled {len(todo)} concepts")
db.close()