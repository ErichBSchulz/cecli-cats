# Plan: Aggregate Command

## Objective

Create a new command `aggregate` for `cecli-cat` that scans directories for test
runs, collects results, enriches them with metadata (UUID, hash) from either
`cat.yaml` (new style) or `index.csv` (classic style), and saves the aggregated
data.

## Input

- A directory containing one or more "run" directories.
- "Run" directories follow a naming convention (likely
  `YYYY-MM-DD-HH-MM-SS--NAME`).

## Processing Steps

1.  **Scan for Runs**: Iterate through subdirectories of the input path.
2.  **Parse Run Info**: Extract timestamp and run name/model name from the
    directory name.
3.  **Scan for Tests**: Inside each run directory, find test results.
    - Test results are likely indicated by the presence of `.aider.results.json`
      (based on README).
4.  **Resolve Metadata**:
    - **New Style**: If `cat.yaml` exists in the test directory, read `uuid` and
      `hash` from it.
    - **Classic Style**: If no `cat.yaml`, deduce the test identity from the
      path (e.g., `python/exercises/practice/bowling`). Look up `uuid` and
      `hash` in `cat/index.csv`.
5.  **Aggregation**: Collect all test results for a run.
6.  **Output**: Save the aggregated results to `runs/MODELNAME/RUNNAME`.

## Questions to Clarify

1.  **Run Directory parsing**: How should we parse
    `2025-12-22-21-07-56--GH200-devstral-small-2:24b-instruct-2512-fp16`?
    - Is the "Model Name" `GH200-devstral-small-2:24b-instruct-2512-fp16`?
    - Is the "Run Name" the timestamp? Or the whole string?
    - The requirement says "save aggregated data into /runs/MODELNAME/RUNNAME".
      We need to know how to split the source directory name into these two
      components, or if they come from elsewhere.
2.  **Result File**: Can we confirm we are looking for `.aider.results.json`
    files to identify a test attempt?
3.  **Output Format**: What format should the aggregated data be saved in? JSON?
    CSV?
4.  **Index Location**: Should we assume `cat/index.csv` exists in the current
    working directory or allow it to be specified?

## Implementation Plan

1.  Create `src/cecli_cat/commands/aggregate.py`.
2.  Implement `load_index(index_path)` to load the classic test mapping.
3.  Implement `scan_runs(input_dir)` to find run directories.
4.  Implement `process_run(run_dir, index)` to walk the run directory, find
    tests, and resolve metadata.
5.  Implement `save_aggregation(data, output_dir)`.
6.  Register the command in `src/cecli_cat/main.py`.
