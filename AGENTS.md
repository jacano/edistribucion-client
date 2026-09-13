# AGENTS.md

This file tells an LLM agent what this tool is and how to use it.

## Language

- Write everything in English. This includes file names, code, messages, and
  documents.
- Use Simple English. Use short sentences. Use the active voice. One word means
  one thing.
- Keep each instruction under 20 words and each description under 25 words.

## What this tool is

- `edistribucion.py` is a command line tool.
- It reads electricity consumption from the e-distribucion private area
  (Endesa group) for the user's own account.
- It uses HTTP only. It uses no browser and no third-party package.
- It talks to the portal with the saved session cookie.

## When to use it

Use it when the user asks for:

- their electricity consumption (kWh) for a month or a date range,
- the split by tariff period P1, P2, P3,
- whether the values are measured or estimated,
- their supplies (CUPS) and the contracted power.

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
| `python edistribucion.py status` | account and supplies with contracted power |
| `python edistribucion.py cups` | full supply list |
| `python edistribucion.py periods` | contracts and the available date range |
| `python edistribucion.py month --month YYYY-MM` | consumption for one month |
| `python edistribucion.py range --from YYYY-MM-DD --to YYYY-MM-DD` | consumption for a range |
| `python edistribucion.py login-backend` | log in with user and password, no browser |
| `python edistribucion.py import-cookies` | import a cookies.txt |
| `python edistribucion.py save --sid` | store a session value by hand |

Add `--json` to `month` or `range` to get raw JSON. Use `--json` when you need
the data for more work.

Add `--cont <contractId>` to pick a supply. Without it, the tool uses the open
contract. The command `cups` shows each `contract_id`.

The options `--sid` and `--session` go before or after the command.

## What the output means

The summary has these keys:

| key | meaning |
| --- | ------- |
| `cups` | the supply identifier |
| `total_kwh` | total consumption for the range |
| `periods_kwh` | object with `P1`, `P2`, `P3` totals in kWh |
| `measured_kwh` | kWh from real measurements |
| `estimated_kwh` | kWh from estimates |
| `measured_hours` | count of measured hours |
| `estimated_hours` | count of estimated hours |
| `peak_demand_kw` | the maximum demand in the range |
| `contracted_power_kw` | the contracted power of the supply. Example: `{"P1": 4.0}` |
| `days` | list of days. Each day has `date`, `kwh`, `periods`, and `kind` |

The `kind` of a day is one of `measured`, `estimated`, `mixed`, or `no_data`.

The `hourly` list has one row per hour. Each row has `date`, `hour`, `kwh`,
`period` (`P1`, `P2`, `P3`), `method` (`measured` or `estimated`), and `real`.

## Rules for your answer

- Always report the split by P1, P2, P3.
- Report the contracted power and the peak demand.
- Always say if the values are measured or estimated. If a day is estimated, say
  so.
- Report the date range that the tool used. The available range can be smaller
  than the range you asked for.
- Do not print the session cookie or the file `session.json`.
- This tool reads data only. Do not try to change data on the portal.

## Examples

Month consumption:

```bash
python edistribucion.py month --month 2026-09
```

Month consumption as JSON:

```bash
python edistribucion.py month --month 2026-09 --json
```

A date range on one supply:

```bash
python edistribucion.py range --from 2026-09-01 --to 2026-09-15 --cont a0ucj00000PYiwHAAT
```

## Errors you can see

| message | what to do |
| ------- | ---------- |
| `Could not obtain aura.token (expired session?)` | the session expired. Tell the user to run `login-backend`. |
| `Aura error ...` | the portal returned an error. Show the message. |
| `No sid found in the text.` | the pasted text had no session. Ask for the `Cookie` header again. |

## Files

- `edistribucion.py`: the tool.
- `AUTHENTICATION.md`: how to get the session.
- `README.md`: the main guide.
