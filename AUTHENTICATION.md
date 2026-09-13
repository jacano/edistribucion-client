# Authentication

The starting point is always the tool. Run the `login` command. The tool opens
the e-distribucion login page. Log in to the portal. Then choose one of three
options to return the session to the tool.

```bash
python edistribucion.py login
```

The tool asks:

```
Log in to the portal. Then choose how to return the session:
  1. Paste a line from DevTools (the Cookie header, or 'Copy as cURL').
  2. Import a cookies.txt file.
  3. Let the agent read it with the Chrome MCP.
Choose 1, 2 or 3 [1]:
```

You can pick the option in advance with `--method`:

```bash
python edistribucion.py login --method 1
```

All three options end with the same result. The file `sesion.json` holds the
session. The session is the `sid` cookie.

## Option 1: paste a line from DevTools

This option needs no extra tool.

1. Log in to the portal.
2. Open DevTools. Press F12.
3. Open the Network tab.
4. Click a request to the portal, for example one named `aura`.
5. Open Headers, then Request Headers. Copy the value of `Cookie`.
6. Paste the value in the tool. Press Enter.

The tool finds the `sid` value in the text.

You can also copy a full request line:

1. Right-click a request in the Network tab.
2. Select Copy, then "Copy as cURL".
3. Paste the whole line in the tool. Press Enter.

The tool finds the `sid` value in the cURL line.

## Option 2: import a cookies file

This option uses a browser extension that exports cookies. One example is
"Get cookies.txt LOCALLY":
`https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc`

1. Log in to the portal.
2. Open the extension on the portal page.
3. Export the cookies. Save the file. The usual name is `cookies.txt`.
4. In the tool, type the file path. Press Enter.

You can also import the file directly, without the menu:

```bash
python edistribucion.py import-cookies cookies.txt
```

## Option 3: let the agent read the session

This option uses the Chrome DevTools MCP with your normal Chrome.

1. Log in to the portal.
2. At the menu, choose 3. The tool shows the next step.
3. Ask the agent: "save my e-distribucion session".
4. The agent reads the `sid` value with the Chrome DevTools MCP. It reads the
   `Cookie` header of a portal request.
5. The agent calls the tool `edist_save_session` with the value.
6. The tool writes `sesion.json`.

Turn on remote debugging one time:

1. Open `chrome://inspect/#remote-debugging`.
2. Turn on Remote debugging.
3. When the agent connects, Chrome asks for permission. Click Allow.

## Direct options

You can also skip the menu.

Save the `sid` value directly.

```bash
python edistribucion.py save --sid "<sid value>"
```

Pass the `sid` value on each command.

```bash
python edistribucion.py month --month 2026-09 --sid "<sid value>"
```

Use the environment variable `EDIST_SID`.

```bash
set EDIST_SID=<sid value>
python edistribucion.py status
```

## Notes

- The `sid` cookie is HttpOnly. A web page cannot read it. The DevTools, an
  extension, or the Chrome MCP can read it.
- Do not share `sesion.json`. It is your live session.
- When a command fails with an authentication error, run `login` again. The
  session expired.
- The `aura.token` refreshes on each call. You do not manage it.
