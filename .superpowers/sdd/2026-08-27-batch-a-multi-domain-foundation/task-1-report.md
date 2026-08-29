# Task 1 Report: Install optional embedding dependency

## Status

DONE

## Commits

- `ab5b9f3` — chore(deps): add sentence-transformers as optional dev dependency

## Test Summary

- `pip install -r requirements-dev.txt` completed without error.
- `python -c "from sentence_transformers import SentenceTransformer; print('ok')"` printed `ok`.

## Concerns

None.
