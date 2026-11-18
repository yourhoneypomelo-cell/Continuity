# tools/

`ws.py` — the command-line tool every agent runs. It validates writes, assigns IDs, runs acceptance tests, seals checkpoints and prints the brief. `wslib/` holds its modules. Standard-library **Python 3.9+**, no packages.

`ws` / `ws.cmd` — launchers that pick the first of `python3`, `python` and `py -3` that is Python 3.9 or newer, then run `ws.py`. Prefer these on macOS, where `python` is often missing.
