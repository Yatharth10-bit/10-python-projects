# BatchProof

Both CSVs total ₹800. One invoice is short ₹10 while another is over by exactly ₹10. BatchProof compares individual invoices to reveal the two discrepancies, even when rows arrive in a different order.

## Run the sample

Python 3.10+, standard library. Run from this folder:

```sh
python batch_proof.py demo
python -m unittest discover -v
python batch_proof.py compare examples/expected.csv examples/received.csv --check
```

The sample returns one matched invoice, two mismatches and a zero difference between totals. In `--check` mode exit code 1 means exceptions were found. Exit code 2 signals invalid input such as a missing file or invalid CSV header. Without `--check`, a successfully generated report exits 0.

## Use your own CSVs

Supply UTF-8 CSVs with the columns `invoice_id` and `amount`, in either order. Each invoice should have one row on each side. The amount is a rupee decimal with at most two fractional digits. Negative values handle credits. Your report includes per-invoice classification, original line numbers and integer amounts in paise. The totals include all parseable amounts with an invoice ID, including duplicate rows. Inspect the exceptions before interpreting those totals.

Try deleting one invoice, repeating a second invoice ID and changing a third amount to `TBD`. Rejected rows appear separately. IDs with duplicates are flagged for review before any amount comparison. An unidentified row can only appear in the rejected-row list.

## What to explain

Hash maps group the two files by ID. A final sort keeps reports deterministic. Integer conversion preserves paise for large inputs. The approach uses memory proportional to the input row count and assumes one currency and one payment per invoice. It makes no fuzzy matches or guesses about split payments.
