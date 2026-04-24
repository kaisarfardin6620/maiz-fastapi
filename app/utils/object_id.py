from bson import ObjectId


def str_to_objectid(id: str) -> ObjectId:
    try:
        return ObjectId(id)
    except Exception:
        raise ValueError(f"Invalid ObjectId: {id}")


def doc_to_dict(doc: dict) -> dict:
    if doc is None:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc


def docs_to_list(docs: list) -> list:
    return [doc_to_dict(doc) for doc in docs]