# e-distribucion client

This tool reads your electricity consumption from the e-distribucion private
area (Endesa group). It uses HTTP only. It runs in the terminal. It also works
as an MCP server for agents.

The client uses HTTP only. It uses only the Python standard library. One
optional command opens your browser to the login page. The client never
controls the browser.

Warning: this tool is not official. It is not connected to e-distribucion or
Endesa. Use it only with your own account. The portal can change at any time.

## How it works

The portal is a Salesforce Experience Cloud site. The session is the `sid`
cookie.

The portal also needs an anti-CSRF token. The token name is `aura.token`. You
do not decode this token. The server sends the token in the `Set-Cookie`
header `__Host-ERIC_PROD...=eyJ...` each time a community page loads. The client
reads the token there and uses it again.

The flow has two steps. One GET request gets a token. Then the client sends
POST requests to `/s/sfsites/aura`.

## Requirements

- Python 3.9 or newer.
- Optional, for `login-proxy`: the `cryptography` package
  (`pip install cryptography`).

## Setup

1. Open `https://zonaprivada.edistribucion.com/areaprivada/s/` in your browser.
2. Log in.
3. Copy the `sid` cookie value. In DevTools, open Application, then Cookies,
   then `zonaprivada.edistribucion.com`, then `sid`.
4. Save the value:

```bash
python edistribucion.py save --sid "<sid cookie value>"
```

You can also put the value in the environment variable `EDIST_SID`.

## Easier way to get the sid

You can use the browser extension "Get cookies.txt LOCALLY" to export the
cookies. Link:

https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc

Steps:

1. Log in to the portal.
2. Open the extension on the portal page.
3. Export the cookies for this site. Save the file.
4. Import the file:

```bash
python edistribucion.py import-cookies cookies.txt
```

The command reads the `sid` cookie and saves it to `sesion.json`. The command
also accepts a JSON export.

## Login command

The command `login` opens the login page in your browser. Then it asks for the
`sid` value.

```bash
python edistribucion.py login
```

Steps:

1. Run the command. Your browser opens the login page.
2. Log in.
3. Open DevTools. Select Application, then Cookies.
4. Select `zonaprivada.edistribucion.com`.
5. Copy the value of `sid`.
6. Paste the value in the terminal.

The command saves the value and checks the session.

The `sid` cookie is HttpOnly. The browser hides it from scripts. A custom
protocol callback gets data from the page URL. The page cannot read an HttpOnly
cookie. So the callback cannot carry the `sid`. That is why this step is
manual.

## DevTools login (agent)

This flow uses your normal Chrome with the `chrome-devtools` MCP. No extension,
no bookmark, no proxy. The agent reads the `sid` value and sends it to our app.

1. Log in to the portal in Chrome.
2. Ask the agent: "save my e-distribucion session".
3. The agent reads the `sid` value with the Chrome DevTools MCP. It reads the
   `Cookie` header of a portal request.
4. The agent calls the tool `edist_save_session` with the value.
5. The tool saves the session. Later commands use plain HTTP.

Turn on remote debugging once:

- Open `chrome://inspect/#remote-debugging`.
- Turn on Remote Debugging.
- When the agent connects, Chrome asks for permission. Click Allow.

## Proxy login

This flow captures the session without an extension and without a bookmark. It
uses your normal Chrome profile. So it keeps your settings and your logins.

Chrome allows one instance per profile. Close Chrome first, or use `--force`.

1. Install the optional dependency.

```bash
pip install cryptography
```

2. Close Chrome.
3. Run the command.

```bash
python edistribucion.py login-proxy
```

Add `--force` to let the tool close Chrome for you:

```bash
python edistribucion.py login-proxy --force
```

4. Chrome opens with your normal profile, through the proxy.
5. Log in to the portal.
6. The tool reads the `sid` cookie, saves it, and reopens Chrome without the
   proxy.

Only the login goes through the proxy. Later commands use plain HTTP with the
saved cookie.

If the login page does not load, trust the printed `ca.crt` file. Then run the
command again. The proxy uses HTTP/1.1 so the headers stay readable.

## Bridge extension

This flow reads your session cookie and sends it to the tool. No bookmark. No
copy-paste. This works because a browser extension may read HttpOnly cookies.

1. Register the protocol. Windows only.

```bash
python edistribucion.py register
```

2. Load the extension:
   - Open `chrome://extensions`.
   - Turn on Developer mode.
   - Click "Load unpacked".
   - Select the `extension` folder in this repo.

3. Open the private area and log in.
4. Click the extension button in the toolbar.
5. Chrome asks to open "e-distribucion bridge". Allow it. Check the box to
   remember the choice.
6. The tool saves the session. Now run any command, for example:

```bash
python edistribucion.py month --month 2026-09
```

The extension sends only the needed cookies: `sid`, `oid`, `sid_Client`,
`inst`, `clientSrc`. The `sid` cookie is HttpOnly. An extension can read it.

## Bookmarklet callback

This flow does not need the `sid` cookie. The page runs the query for you.

1. Register the protocol. Windows only.

```bash
python edistribucion.py register
```

2. Print the bookmarklet code.

```bash
python edistribucion.py bookmarklet
```

3. Create a bookmark in your browser. Use the printed text as the URL.
4. Open the private area and log in.
5. Click the bookmark and answer the prompt. Example answers:
   - `status`
   - `month 2026-09`
   - `range 2026-09-01 2026-09-30`
6. The page sends the result to the tool. The tool saves the result in
   `callback.json`.
7. Show the result.

```bash
python edistribucion.py callback
```

The agent uses the tool `edist_read_callback` to read the same file.

This flow runs one query per click, and you must be logged in. The flow with
`sesion.json` runs without you. Use the bookmarklet flow when the session is
hard to copy.

## Commands

```bash
# Account and supplies. Shows the contracted power.
python edistribucion.py status

# Full supply list with all fields.
python edistribucion.py cups

# Billing periods, contracts, and the available date range.
python edistribucion.py periods

# Consumption for one month. Splits P1, P2 and P3. Marks real or estimated.
python edistribucion.py month --month 2026-09

# Consumption for a date range.
python edistribucion.py range --from 2026-09-01 --to 2026-09-30

# JSON output.
python edistribucion.py month --month 2026-09 --json
```

Example output:

```
Month 2026-09 (available 2026-09-04 -> 2026-09-12)
CUPS: ES0031...WR0F | contractId: a0ucj...
Range: 2026-09-04 -> 2026-09-12
Total: 61.153 kWh | peak demand: 14.683000000000002 kW
Periods (kWh): {'P3': 16.137, 'P2': 20.779, 'P1': 24.237}
Measured: 61.153 kWh (192 h) | Estimated: 0.0 kWh (24 h)

Daily detail:
  04/09/2026     2.336 kWh  MEASURED  {'P3': 0.781, 'P2': 0.783, 'P1': 0.772}
  ...
  12/09/2026     0.000 kWh  ESTIMATED {}
```

## Output fields

Each hour has these fields.

| field      | meaning                                  |
| ---------- | ---------------------------------------- |
| `kwh`      | consumption for the hour                 |
| `period`   | tariff period: `P1`, `P2`, or `P3`       |
| `method`   | `measured` (R) or `estimated` (E)        |
| `real`     | true when the value is a real measure    |
| `invoiced` | true when the value is already invoiced  |
| `valid`    | true when the hour is valid              |

The command `cups` shows the contracted power for each supply. Example:
`{"P1": 4.0}`.

## MCP server

The file `mcp_server.py` gives the client to an agent. It speaks MCP over
stdio. Configuration example:

```json
{
  "mcp": {
    "edistribucion": {
      "type": "local",
      "command": ["python", "/absolute/path/to/mcp_server.py"],
      "enabled": true
    }
  }
}
```

Tools:

| tool                      | description                                          |
| ------------------------- | ---------------------------------------------------- |
| `edist_status`            | account and supplies with contracted power           |
| `edist_supplies`          | full supply list                                     |
| `edist_periods`           | billing periods, contracts, and available range      |
| `edist_month_consumption` | month consumption by P1/P2/P3, real or estimated     |
| `edist_range_consumption` | consumption for a date range by P1/P2/P3             |

The server reads the session from `EDIST_SID` or from `sesion.json`.

## Session

The `sid` session ends after some time. If a command fails with an
authentication error, copy a new `sid` and run `save` again.

The client refreshes the `aura.token` on each call. The token lives about 60
seconds.

## Security

The file `sesion.json` holds your live session cookie. The `.gitignore` file
excludes this file. Do not commit it. Do not share it.

The client reads data from your own account only.

## License

MIT. See the `LICENSE` file.
