from pinecone import Pinecone

pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
index = pc.Index("support-rag-bot")
index.upsert(vectors=[(c.id, embed(c.text), c.meta) for c in chunks])
