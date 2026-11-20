"""Compare two OpenAPI JSON documents from an existing client's perspective."""

import argparse
import json
import sys
from pathlib import Path

METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
ANNOTATIONS = {"title", "description", "example", "examples", "default", "deprecated",
               "externalDocs", "summary", "operationId", "tags"}
SCHEMA_KEYS = {"type", "enum", "properties", "required"}
MISSING = object()


def read_spec(path):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not str(doc.get("openapi", "")).startswith("3.1."):
        raise ValueError("expected an OpenAPI 3.1.x JSON document")
    if not isinstance(doc.get("paths"), dict):
        raise ValueError("expected a paths object")
    return doc


def object_ref(schema, doc):
    """Resolve simple document-local JSON pointers; leave other forms for review."""
    seen = set()
    while isinstance(schema, dict) and "$ref" in schema:
        ref = schema["$ref"]
        if (not isinstance(ref, str) or not ref.startswith("#/") or ref in seen
                or set(schema) - {"$ref"} - ANNOTATIONS):
            return None
        seen.add(ref)
        schema = doc
        for piece in ref[2:].split("/"):
            key = piece.replace("~1", "/").replace("~0", "~")
            if not isinstance(schema, dict) or key not in schema:
                raise ValueError(f"unresolved local reference {ref}")
            schema = schema[key]
    return schema


def changes(old, new):
    rows = []

    def record(level, where, message):
        rows.append({"level": level, "location": where, "reason": message})

    def other_changed(before, after, known):
        keys = (before.keys() | after.keys()) - known - ANNOTATIONS
        return sorted(k for k in keys if before.get(k, MISSING) != after.get(k, MISSING))

    def schema_diff(a, b, where, request, ancestors):
        a, b = object_ref(a, old), object_ref(b, new)
        if not isinstance(a, dict) or not isinstance(b, dict):
            record("review", where, "Boolean, external or compound reference needs review")
            return
        pair = (id(a), id(b))
        if pair in ancestors:
            return
        # The narrower side must remain a subset of the wider one.
        small, large = (a, b) if request else (b, a)
        small_type, large_type = small.get("type"), large.get("type")
        if isinstance(small_type, list) or isinstance(large_type, list):
            record("review", where, "Union type needs review")
        elif large_type and small_type != large_type and (small_type, large_type) != ("integer", "number"):
            record("break", where, f"Type changed from {a.get('type', 'unrestricted')} to {b.get('type', 'unrestricted')}")
        if "enum" in large:
            # JSON encoding distinguishes booleans from integer values.
            def enum_values(s):
                return {json.dumps(v, sort_keys=True) for v in s["enum"]}
            if "enum" not in small or not enum_values(small) <= enum_values(large):
                record("break", where, "Accepted input enum narrowed" if request else "Possible output enum widened")
        req_a, req_b = set(a.get("required", [])), set(b.get("required", []))
        for field in sorted(req_b - req_a if request else req_a - req_b):
            record("break", f"{where}.{field}", "New required input" if request else "Output no longer guaranteed")
        for key in other_changed(a, b, SCHEMA_KEYS):
            record("review", where, f"Schema keyword changed: {key}")
        props_a, props_b = a.get("properties", {}), b.get("properties", {})
        for key in sorted(props_a.keys() | props_b.keys()):
            # Absent property schemas permit arbitrary values by default. A
            # closed/typed additionalProperties instead supplies that schema.
            child_a = props_a.get(key, a.get("additionalProperties", {}))
            child_b = props_b.get(key, b.get("additionalProperties", {}))
            if key not in props_a or key not in props_b:
                if (request and key not in props_a) or (not request and key not in props_b):
                    # Newly declared optional fields often intentionally extend
                    # an API. Whether existing consumers send/read them varies.
                    record("review", f"{where}.{key}", "Property declaration changed; check existing clients")
                    continue
            schema_diff(child_a, child_b, f"{where}.{key}", request, ancestors | {pair})

    def body_diff(a, b, where, request):
        if "$ref" in a or "$ref" in b:
            record("review", where, "Body/response object reference needs review")
            return
        if request and b.get("required") and not a.get("required"):
            record("break", where, "Request body became required")
        content_a, content_b = a.get("content", {}), b.get("content", {})
        for media in sorted(content_a.keys() | content_b.keys()):
            if media not in content_b:
                record("break", where, f"Previously documented media type removed: {media}")
            elif media not in content_a:
                if not request and content_a:
                    record("review", where, f"New response media type: {media}")
            elif media == "application/json":
                schema_diff(content_a[media].get("schema", {}), content_b[media].get("schema", {}),
                            where, request, set())
            elif content_a[media] != content_b[media]:
                record("review", where, f"Media definition changed: {media}")
        for key in other_changed(a, b, {"content", "required"}):
            record("review", where, f"Definition changed: {key}")

    for path, path_old in sorted(old["paths"].items()):
        path_new = new["paths"].get(path, {})
        for method in sorted(path_old.keys() & METHODS):
            where = f"{method.upper()} {path}"
            if method not in path_new:
                record("break", where, "Endpoint removed")
                continue
            a, b = path_old[method], path_new[method]
            for key in other_changed(a, b, {"requestBody", "responses"}):
                record("review", where, f"Operation field changed: {key}")
            body_diff(a.get("requestBody", {}), b.get("requestBody", {}), f"{where} request", True)
            ra, rb = a.get("responses", {}), b.get("responses", {})
            for code in sorted(ra.keys() | rb.keys()):
                if code not in rb:
                    record("review", where, f"Response status removed: {code}")
                elif code not in ra:
                    record("review", where, f"New response status: {code}")
                else:
                    body_diff(ra[code], rb[code], f"{where} response {code}", False)
        for key in other_changed(path_old, path_new, METHODS):
            record("review", path, f"Path-level field changed: {key}")
    for key in other_changed(old, new, {"paths", "components", "info", "openapi"}):
        record("review", "document", f"Document field changed: {key}")
    components_a, components_b = old.get("components", {}), new.get("components", {})
    for key in other_changed(components_a, components_b, {"schemas"}):
        record("review", "components", f"Shared definitions changed: {key}")
    return rows


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--json", action="store_true", help="machine-readable findings")
    options = parser.parse_args(args)
    try:
        result = changes(read_spec(options.before), read_spec(options.after))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    if options.json:
        print(json.dumps(result, indent=2))
    elif result:
        for row in result:
            print(f"{row['level'].upper():6}  {row['location']}  |  {row['reason']}")
    else:
        print("No changes flagged by the supported checks.")
    if any(r["level"] == "break" for r in result):
        return 1
    return 3 if result else 0


if __name__ == "__main__":
    raise SystemExit(main())
