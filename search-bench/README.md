# Search Bench

Search a campus handbook for **graphics lab**. With equal weights, a newsletter that repeats the phrase outranks the access instructions. Boost the title field and the access instructions move from second to first. A different query, **wifi**, still misses the wireless network guide.

## Run locally

Use Python with SQLite FTS5 enabled, as in standard python.org desktop installations. From this folder run:

```sh
python search_bench.py query "graphics lab"
python search_bench.py eval
python search_bench.py --weight 1 query "graphics lab"
python search_bench.py serve
```

The last command starts a local read-only JSON API at <http://127.0.0.1:8765/search?q=graphics+lab>. Stop it with Ctrl+C. Use `python -m unittest discover -v` to test ranking, evaluation, input errors and HTTP responses.

## Measure the difference

The bundled fictional campus has twelve original documents and nine hand-labeled queries. For each query the evaluator takes the reciprocal rank of the first relevant document in the top three. A miss scores zero. The mean of those scores is MRR@3.

| Ranking rule | MRR@3 | Graphics lab guide |
|---|---:|---:|
| BM25 with equal weights | 0.722 | 2nd |
| BM25 with a 5× title weight | 0.889 | 1st |

These scores describe this small, authored fixture. They illustrate a ranking regression test. For an independent evaluation, collect separate queries before adjusting the weights. The lexical matcher has no synonym dictionary. A title boost cannot recover a document that matches none of the query terms.

## Try another collection

Supply UTF-8 CSV files with the same headers as [documents.csv](documents.csv) and [judgments.csv](judgments.csv). Repeat a query across rows to mark multiple relevant documents. IDs must be unique in the corpus.

```sh
python search_bench.py --docs my_docs.csv --weight 2 -k 5 eval --labels my_labels.csv
```

The tool creates an in-memory FTS5 index per invocation and uses parameterized SQL. Each query becomes an OR of literal tokens. Results include highlighted matching words and use document ID to break score ties. The HTTP server is single-process and bound to localhost for demonstrations.

Reference: [SQLite's BM25 implementation and column weights](https://www.sqlite.org/fts5.html#the_bm25_function).
