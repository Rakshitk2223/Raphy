import json
import uuid
from pathlib import Path
from typing import Optional

import chromadb
from sentence_transformers import SentenceTransformer

from backend.config import settings

_embedding_model = None


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        print("Loading embedding model...")
        _embedding_model = SentenceTransformer(settings.embedding_model)
        print("Embedding model loaded!")
    return _embedding_model


class MemoryStore:
    def __init__(self):
        self.notes_file = settings.notes_dir / "notes.json"
        self.notes_file.parent.mkdir(parents=True, exist_ok=True)

        self._chroma_client = None
        self._collection = None
        self._embedding_model = None

    @property
    def chroma_client(self):
        if self._chroma_client is None:
            self._chroma_client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        return self._chroma_client

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.chroma_client.get_or_create_collection("knowledge")
        return self._collection

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            self._embedding_model = SentenceTransformer(settings.embedding_model)
        return self._embedding_model

    def load_notes(self) -> dict:
        if self.notes_file.exists():
            try:
                return json.loads(self.notes_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def save_notes(self, notes: dict):
        self.notes_file.write_text(
            json.dumps(notes, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def add_note(self, key: str, value: str) -> dict:
        notes = self.load_notes()
        note_id = str(uuid.uuid4())[:8]
        notes[note_id] = {
            "key": key,
            "value": value,
            "created_at": str(Path(__file__).stat().st_ctime),
        }
        self.save_notes(notes)
        return {"id": note_id, "key": key, "value": value}

    def get_note(self, note_id: str) -> Optional[dict]:
        notes = self.load_notes()
        return notes.get(note_id)

    def update_note(
        self, note_id: str, key: Optional[str] = None, value: Optional[str] = None
    ) -> Optional[dict]:
        notes = self.load_notes()
        if note_id not in notes:
            return None

        if key is not None:
            notes[note_id]["key"] = key
        if value is not None:
            notes[note_id]["value"] = value

        self.save_notes(notes)
        return notes[note_id]

    def delete_note(self, note_id: str) -> bool:
        notes = self.load_notes()
        if note_id in notes:
            del notes[note_id]
            self.save_notes(notes)
            return True
        return False

    def list_notes(self) -> list[dict]:
        notes = self.load_notes()
        return [
            {"id": note_id, "key": data["key"], "value": data["value"]}
            for note_id, data in notes.items()
        ]

    def search_knowledge(self, query: str, top_k: int = 5) -> list[dict]:
        if self.collection.count() == 0:
            return []

        model = get_embedding_model()
        query_embedding = model.encode([query]).tolist()
        results = self.collection.query(query_embeddings=query_embedding, n_results=top_k)

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        return [
            {"content": doc, "source": meta.get("source", "unknown"), "score": 1 - dist}
            for doc, meta, dist in zip(documents, metadatas, distances)
        ]


memory_store = MemoryStore()
