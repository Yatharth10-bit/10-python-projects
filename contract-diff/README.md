# Contract Diff

Would your last client's order still work after an API release? Compare two OpenAPI 3.1 JSON files from the perspective of an existing client. The included ticket-booking API introduces two changes. A previously valid order omitting `seats` now fails, and a client that handles only `confirmed` may receive `waitlisted`.

## Run

Python 3.9+, standard library. From this folder:

```sh
python contract_diff.py examples/v1.json examples/v2.json
python contract_diff.py examples/v1.json examples/v2.json --json
python -m unittest discover -v
```

The sample returns exit **1** and reports both field paths. Reverse the inputs to see how the same edits can be compatible in the opposite release direction.

| Exit | Meaning |
|---|---|
| 0 | No findings within the supported checks |
| 1 | Breaking change detected |
| 2 | Input could not be read or processed |
| 3 | Changes require human review |

## What it checks

Checks removed operations, JSON media types, required request fields, guaranteed response fields, simple scalar types, enum direction and nested object properties. Resolves document-local `$ref` pointers to schemas and handles recursive pairs. New endpoints are additive. New response codes, changed operation parameters and changed constraints such as `minLength` go to review.

The model assumes clients may send any documented valid request and expect the documented JSON response shape. No server calls are made. Supply valid specifications: this tool does not validate the entire OpenAPI standard. Arrays, unions, alternate media, discriminators, non-schema component references, external references, detailed status fallback, nested refs inside unsupported constructs and advanced JSON Schema interactions require human analysis. The comparison deliberately flags some edits conservatively. Integer-valued floats and integers written differently inside an enum may be flagged. A clean run covers only the implemented rules.

[OpenAPI 3.1 specification](https://spec.openapis.org/oas/v3.1)
