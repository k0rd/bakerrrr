from __future__ import annotations

METADATA_KEY = "_meta"
SCHEMA_VERSION = 1


def build_schema_metadata(meta=None, *, schema_version=SCHEMA_VERSION):
    metadata = dict(meta) if isinstance(meta, dict) else {}
    metadata["schema_version"] = int(schema_version)
    return metadata


def split_object_document(raw):
    if not isinstance(raw, dict):
        return None, {}
    metadata = raw.get(METADATA_KEY)
    payload = {
        key: value
        for key, value in raw.items()
        if key != METADATA_KEY
    }
    return payload, metadata if isinstance(metadata, dict) else {}


def wrap_object_document(payload, *, meta=None, schema_version=SCHEMA_VERSION):
    source = payload if isinstance(payload, dict) else {}
    document = {
        METADATA_KEY: build_schema_metadata(meta, schema_version=schema_version),
    }
    for key, value in source.items():
        if key == METADATA_KEY:
            continue
        document[key] = value
    return document


def split_sequence_document(raw, *, sequence_key):
    if isinstance(raw, list):
        return list(raw), {}, {}
    if not isinstance(raw, dict):
        return None, {}, {}
    metadata = raw.get(METADATA_KEY)
    extras = {
        key: value
        for key, value in raw.items()
        if key not in {METADATA_KEY, sequence_key}
    }
    sequence = raw.get(sequence_key)
    if not isinstance(sequence, list):
        return None, metadata if isinstance(metadata, dict) else {}, extras
    return list(sequence), metadata if isinstance(metadata, dict) else {}, extras


def wrap_sequence_document(sequence, *, sequence_key, meta=None, schema_version=SCHEMA_VERSION, extras=None):
    document = {
        METADATA_KEY: build_schema_metadata(meta, schema_version=schema_version),
        sequence_key: list(sequence) if isinstance(sequence, (list, tuple)) else [],
    }
    if isinstance(extras, dict):
        for key, value in extras.items():
            if key in {METADATA_KEY, sequence_key}:
                continue
            document[key] = value
    return document
