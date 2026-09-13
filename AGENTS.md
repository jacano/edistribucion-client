# AGENTS.md

This file tells an LLM agent what this tool is and how to use it.

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
- The tool needs the session file `sesion.json`.
- If a command fails with an authentication error, the session expired. Tell the
  user to run `python edistribucion.py login` and follow the steps. See
  `AUTHENTICATION.md`.

## Capture the session from Chrome (agent)

Use this when the user asks you to capture the session, and the Chrome DevTools
MCP is available.

Before you start:

- The user must log in to the portal in Chrome.
- Remote debugging must be on: `chrome://inspect/#remote-debugging`.
- When you connect, Chrome asks the user for permission. The user clicks Allow.

Steps:

1. Use the MCP tool `list_pages`. Find the page with
   `zonaprivada.edistribucion.com`.
2. Use `list_network_requests` for that page. Filter on `xhr` and `fetch`. Find
   a request with the path `/s/sfsites/aura`. If there is none, ask the user to
   open the private area and click a menu item.
3. Use `get_network_request` on that request. Read the request header `cookie`.
4. Find `sid=` in the header. Take the value up to the next `;`. The value looks
   like `00D...!AQEA...`.
5. Save it:

```bash
python edistribucion.py save --sid "<sid value>"
```

Or pass the whole header:

```bash
python edistribucion.py save --text "<cookie header>"
```

6. Check the session with `python edistribucion.py status`.

Do not print the `sid` value in the chat. It is a secret.

## Commands

Use these commands. Do not guess new ones.

| command | what it does |
| --------- | ------------ |
| `python edistribucion.py status` | account and supplies with contracted power |
| `python edistribucion.py cups` | full supply list |
| `python edistribucion.py periods` | contracts and the available date range |
| `python edistribucion.py month --month YYYY-MM` | consumption for one month |
| `python edistribucion.py range --from YYYY-MM-DD --to YYYY-MM-DD` | consumption for a range |
| `python edistribucion.py login` | open the login page and save the session |
| `python edistribucion.py login-backend` | log in with user and password, no browser |

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
| `days` | list of days. Each day has `date`, `kwh`, `periods`, and `kind` |

The `kind` of a day is one of `measured`, `estimated`, `mixed`, or `no_data`.

The `hourly` list has one row per hour. Each row has `date`, `hour`, `kwh`,
`period` (`P1`, `P2`, `P3`), `method` (`measured` or `estimated`), and `real`.

## Rules for your answer

- Always report the split by P1, P2, P3.
- Always say if the values are measured or estimated. If a day is estimated, say
  so.
- Report the date range that the tool used. The available range can be smaller
  than the range you asked for.
- Do not print the session cookie or the file `sesion.json`.
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
| `Could not obtain aura.token (expired session?)` | the session expired. Tell the user to run `login`. |
| `Aura error ...` | the portal returned an error. Show the message. |
| `No sid found in the text.` | the pasted text had no session. Ask for the `Cookie` header again. |

## Files

- `edistribucion.py`: the tool.
- `AUTHENTICATION.md`: how to get the session.
- `README.md`: the main guide.
