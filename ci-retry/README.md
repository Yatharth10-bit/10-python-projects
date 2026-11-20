# CI Retry

Your CI check turned green on retry. Which test changed, and did the retry use the same revision and environment? CI Retry compares local JUnit XML reports and prints the evidence for intermittent failures. The supplied fixture is a **synthetic booking pipeline**. Its reservation test recovers on retry, its currency test passes only after a new commit, and its receipt test is skipped on the first run.

## Run

Python 3.9+ with the standard library. From this folder:

```sh
python ci_retry.py examples/runs.json
python ci_retry.py examples/runs.json --json
python ci_retry.py examples/runs.json --fail-on-candidate
python -m unittest discover -v
```

The sample identifies one candidate, `test_reservation`, which failed on attempt 1 and passed on attempt 2. The repeated testcase took **2 seconds**. A skipped observation is recorded in a candidate's history but does not count as a pass or failure. Consistently failing retests count in the consistent group.

## Use your own runs

Produce one JUnit XML file for each complete or partial attempt, for example with `pytest --junit-xml=attempt1.xml`. Create a JSON list based on [the demo manifest](examples/runs.json). Each item identifies the commit SHA, CI workflow run, job, environment, attempt number and file path (relative to the manifest or absolute). Use an environment identifier that distinguishes OS, Python version and test configuration. Jobs that contain sharded reports should use one job identifier per shard. Test identity includes the suite name chain, class and case name.

The tool flags mixed pass/fail outcomes within a single commit/run/job/environment. Either transition direction counts. It cannot infer the root cause or recover outcomes that the test runner omitted. Reported seconds sum testcase durations after its first observed execution, excluding skipped attempts. Missing durations count as zero. Parallel durations are per-test and do not measure elapsed pipeline time or cloud cost.

Input errors exit **2**; ordinary analysis exits **0**. With `--fail-on-candidate`, any mixed outcome exits **1**, suitable for an optional CI gate. Duplicate attempts, duplicate testcase identities and exporters embedding retry results inline are rejected. Use trusted local reports.

[pytest JUnit XML output](https://docs.pytest.org/en/stable/how-to/output.html) · [pytest on flaky tests](https://docs.pytest.org/en/stable/explanation/flaky.html)
