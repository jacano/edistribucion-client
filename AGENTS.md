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
  the user to run `edistribucion login-backend`, or let the auto login do it.
  See `AUTHENTICATION.md`.

## Commands

| command | what it does |
| --------- | ------------ |
| `edistribucion` | full report for every CUPS, all data |
| `edistribucion report` | the same as `edistribucion` |
| `edistribucion login-backend` | log in with user and password, no browser |
| `edistribucion import-cookies` | import a cookies.txt |
| `edistribucion save --sid` | store a session value by hand |

The options `--sid` and `--session` go before or after the command.

## report

```bash
edistribucion
```

This is the full report. It uses all the data available. It gives one report
for each CUPS of the account, one after another. It contains:

- the CUPS id and the contracted power per period,
- the real period used,
- the real and estimated totals and the split by `P1`, `P2`, `P3`,
- the consumption by year (with the P1, P2, P3 split), month, and hour, with
  real and estimated values,
- the maximum consumption in one hour per year,
- the maximum demanded power per year and per month,
- a warning when estimated data exists, with the dates.

Option:

- `--json` gives raw JSON. With several CUPS, the JSON is a list.

The tool writes the progress of each step to stderr. The report, or the JSON,
goes to stdout. So `--json` stays correct when you capture the output.

The tool asks the portal for one zip with the hourly curves (action
`createZip`), waits for it, and reads it. Then it deletes the zip. The period
(P1, P2, P3) comes from the 2.0TD calendar, not from a data call.

The portal has no data before 2024-01-16.

## Rules for your answer

- Report the real and the estimated values separately.
- Always report the split by P1, P2, P3.
- Report the dates for the estimated data.
- Report the contracted power and the peak demand.
- Do not print the session cookie or the file `session.json`.
- This tool reads data only. Do not try to change data on the portal.

## Errors

| message | what to do |
| ------- | ---------- |
| `Could not obtain aura.token (expired session?)` | the session expired. Tell the user to run `login-backend`. |
| `Aura error ...` | the portal returned an error. Show the message. |
| `No sid found in the text.` | the text had no session. Ask for the value again. |

## Files

- `edistribucion.py`: the tool.
- `AUTHENTICATION.md`: how to get the session.
- `TARIFF_2_0TD.md`: the 2.0TD periods and the period calculation.
- `README.md`: the main guide.
