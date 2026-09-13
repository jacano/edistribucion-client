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
- It does three things:
  1. Show the maximum demanded power per month.
  2. Aggregate real consumption by hour, day, month, or year.
  3. Find non-real (estimated) data and when it happens.

## Before you run it

- Run commands from the folder that holds `edistribucion.py`.
- The tool needs the session file `session.json`.
- If a command fails with an authentication error, the session expired. Tell the
  user to run `python edistribucion.py login-backend`, or let the auto login do
  it. See `AUTHENTICATION.md`.

## Commands

Use these commands. Do not guess new ones.

| command | what it does |
| --------- | ------------ |
| `python edistribucion.py cups` | list supplies, with the contracted power and the CUPS id |
| `python edistribucion.py consume --group month` | aggregate consumption by hour, day, month, or year |
| `python edistribucion.py maxpower` | maximum demanded power per month |
| `python edistribucion.py login-backend` | log in with user and password, no browser |
| `python edistribucion.py import-cookies` | import a cookies.txt |
| `python edistribucion.py save --sid` | store a session value by hand |

The options `--sid` and `--session` go before or after the command.

## consume

```bash
python edistribucion.py consume --from 2024-01-16 --to 2026-09-12 --group month
```

- `--group` is `hour`, `day`, `month`, or `year`. The default is `day`.
- `hour` groups by hour of the day (00 to 23).
- `--from` and `--to` are `YYYY-MM-DD`. Without them, it covers the full
  history.
- `--cont` picks one supply. Without it, the tool uses the open contract.
- `--json` gives raw JSON.

The output has these keys:

| key | meaning |
| --- | ------- |
| `from`, `to` | the real period used |
| `group` | the group used |
| `real_kwh` | total measured consumption |
| `estimated_kwh` | total estimated consumption |
| `real_hours`, `estimated_hours` | count of measured and estimated hours |
| `periods_real_kwh` | measured total by `P1`, `P2`, `P3` |
| `estimated_days` | the dates or date ranges with estimated data |
| `groups` | one entry per group with `key`, `real_kwh`, `estimated_kwh`, `real_hours`, `estimated_hours` |

Each request covers up to 35 days. The tool walks the history in 35-day steps.

## maxpower

```bash
python edistribucion.py maxpower
```

- `--from` and `--to` are `YYYY-MM`. The default is the last 12 months.
- `--cont` picks one supply. `--json` gives raw JSON.

The output has these keys:

| key | meaning |
| --- | ------- |
| `requestedPower` | the contracted power in kW |
| `maxValue` | the single maximum, with the date and the time |
| `lstData` | one point per month |

A point with `valid: false` means no data for that month. A valid point has
`value` (the monthly maximum in kW) and `periodData` with the maxima per period.
`T1` is `P1`, `T2` is `P2`, and `T3` is `P3`.

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
- `README.md`: the main guide.
