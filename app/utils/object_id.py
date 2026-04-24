from bson import ObjectId


def str_to_objectid(id: str) -> ObjectId:
    try:
        return ObjectId(id)
    except Exception:
        raise ValueError(f"Invalid ObjectId: {id}")


def doc_to_dict(doc: dict) -> dict:
    if doc is None:
        return None
    return _serialize_document(doc)


def docs_to_list(docs: list) -> list:
    return [doc_to_dict(doc) for doc in docs]


def _serialize_document(value):
    if isinstance(value, ObjectId):
        return str(value)

    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key == "_id":
                out["id"] = _serialize_document(item)
            else:
                out[key] = _serialize_document(item)
        return out

    if isinstance(value, list):
        return [_serialize_document(item) for item in value]

    return value