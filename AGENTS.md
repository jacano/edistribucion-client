# AGENTS.md

This file tells an LLM agent what this tool is and how to use it.

## Language

- Write everything in English. This includes file names, code, messages, and
  documents.
- Use Simple English. Use short sentences. Use the active voice. One word means
  one thing.
- Keep each instruction under 20 words and each description under 25 words.

## What this tool is

- `edistribucion.py` reads electricity data from the e-distribucion private area
  for the user's own account.
- It uses HTTP only. It uses no browser and no third-party package.
- It gives one thing: a full report per CUPS. The report has the real
  consumption, the estimated consumption, and the power.

## Before you run it

- Install the tool with `pip install .` or `pipx install .`. This gives the
  `edistribucion` command.
- You can also run the file: `python edistribucion.py`.
- The tool needs the session file `session.json`. The tool looks for it in the
  folder of the file, the current folder, and the user config folder.
- If the report fails with an authentication error, the session expired. Tell
  the user to run `edistribucion login`, or let the auto login do it.
  See `docs/AUTHENTICATION.md`.

## Commands

| command | what it does |
| --------- | ------------ |
| `edistribucion` | full report for every CUPS, all data |
| `edistribucion report` | the same as `edistribucion` |
| `edistribucion login` | log in with user and password, no browser |
| `edistribucion import-cookies` | import a cookies.txt |
| `edistribucion set-session --sid` | store a session value by hand |

The options `--sid`, `--session`, `--wait`, `--keep-artifacts`, `--quiet`,
`--verbose`, `--zone` and `--export-csv` go before or after the command.

## report

```bash
edistribucion
```

This is the full report. It uses all the data available. It gives one report
for each CUPS of the account, one after another. With several CUPS, it first
prints a summary table, and each report has a banner `CUPS i of N`. It
contains:

- the CUPS, the tariff, and the contracted power per period,
- the period covered (the first and the last date),
- the real and estimated totals and the split by `P1`, `P2`, `P3`,
- the consumption by year (with the P1, P2, P3 split), month, hour, and
  weekday, with real and estimated values,
- the maximum consumption in one hour per year, from the real values,
- the maximum demanded power per year, with the split by power period (P1 and
  P2) and the months above the contracted power (the full list per month is in
  the JSON),
- a zoom of the last 3 months (the last reading and its delay, and the real,
  estimated and pending ranges), and a monthly reading map (R real,
  E estimated, M mixed, . no data; pending days do not count).

Option:

- `--json` gives raw JSON. With several CUPS, the JSON is a list.

The tool writes the progress of each step to stderr. The report, or the JSON,
goes to stdout. So `--json` stays correct when you capture the output.

The tool asks the portal for one zip with the hourly curves (action
`createZip`), waits for it, and reads it. The portal also makes a notification.
Then the tool deletes the zip and the notification. Add `--keep-artifacts` to keep both
on the portal. The period (P1, P2, P3) comes from the 2.0TD calendar and the
zone of the supply, not from a data call. The zone comes from the postal code
(51xxx is Ceuta, 52xxx is Melilla); `--zone` sets it by hand.

The tool does not use the per-range API `getChartPointsByRange`: it covers only
about 35 days per call, so the full history needs many calls and does not scale.

The report shows the tariff. When the tariff is not 2.0TD, the tool stops with
an error and gives no report data.

See `docs/ASSUMPTIONS.md` for the full list of assumptions and limits.

## Rules for your answer

- Report the real and the estimated values separately.
- Always report the split by P1, P2, P3.
- Report the last reading and the recent zoom (real, estimated and pending).
- Report the contracted power and the peak demand.
- Do not print the session cookie or the file `session.json`.
- This tool reads data only. Do not try to change data on the portal.

## Errors

| message | what to do |
| ------- | ---------- |
| `Could not obtain aura.token (expired session?)` | the session expired. Tell the user to run `login`. |
| `Aura error ...` | the portal returned an error. Show the message. |
| `No sid found in the text.` | the text had no session. Ask for the value again. |

## Tests and lint

- `pip install -e ".[dev]"`, then `ruff check .` and `pytest`.
- The tests cover the pure logic only. They need no network and no session.
- CI runs both on push to `main` and on pull requests.

## Commits

Use Conventional Commits. Keep the subject in one line. Add a body only when it
helps.

```
type(scope): short description
```

- Type: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`, `ci`,
  `build`, `style` or `revert`.
- The scope is optional. Use it for one part, for example `report` or `auth`.
- Write the description in the imperative and in the lowercase. Do not end it
  with a period. Keep the subject under 72 characters.
- Add `!` after the type or the scope for a breaking change.

Examples:

```
feat(report): add the reading map
fix(auth): do not repeat the session check
docs: add the architecture diagrams
test: cover the day of the change of the hour
ci: run the checks on Python 3.13
```

## Files

- `edistribucion.py`: the tool.
- `tests/test_edistribucion.py`: the unit tests.
- `pyproject.toml`: the install data, the `edistribucion` command, and the tool
  settings for pytest and ruff.
- `README.md`: the main guide.
- `docs/INSTALL.md`: how to install and run the tool.
- `docs/AUTHENTICATION.md`: how to get the session.
- `docs/ARCHITECTURE.md`: the Aura protocol and the data flows, with diagrams.
- `docs/TARIFF_2_0TD.md`: the 2.0TD periods and the period calculation.
- `docs/ASSUMPTIONS.md`: what the tool assumes, and the limits.
