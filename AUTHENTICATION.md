# Authentication

This document shows the three ways to get the session. Pick one. All three end
with the same result: the file `sesion.json` holds the session.

The session is the `sid` cookie. The tool uses it for every command.

Before you start:

- Open the portal: `https://zonaprivada.edistribucion.com/areaprivada/s/`.
- Log in.

## Flow 1: import a cookies file

Best when you want a simple export from the browser.

What you need:

- A browser extension that exports cookies. One example is "Get cookies.txt
  LOCALLY":
  `https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc`

Steps:

1. Log in to the portal.
2. Open the extension on the portal page.
3. Export the cookies. Save the file. The usual name is `cookies.txt`.
4. Run the import.

```bash
python edistribucion.py import-cookies cookies.txt
```

The command reads the cookies and writes `sesion.json`. The command also
accepts a JSON export.

Check the session.

```bash
python edistribucion.py status
```

## Flow 2: pass the session as an argument

Best when you have the `sid` value and you do not want a file.

Where to find the `sid`:

1. Log in to the portal.
2. Open DevTools. Press F12.
3. Select Application, then Cookies.
4. Select `zonaprivada.edistribucion.com`.
5. Copy the value of `sid`.

Option A. Save the value one time.

```bash
python edistribucion.py save --sid "<sid value>"
```

Option B. Pass the value on each command.

```bash
python edistribucion.py month --month 2026-09 --sid "<sid value>"
```

You can also use the environment variable `EDIST_SID`.

```bash
set EDIST_SID=<sid value>
python edistribucion.py status
```

There is also a helper. The command `login` opens the login page and asks you
to paste the `sid`.

```bash
python edistribucion.py login
```

## Flow 3: use the MCP (agent)

Best when you want the agent to do the work, with your normal Chrome.

What you need:

- The `chrome-devtools` MCP, with remote debugging turned on.
- The `edistribucion` MCP server.

Turn on remote debugging one time:

1. Open `chrome://inspect/#remote-debugging`.
2. Turn on Remote debugging.
3. When the agent connects, Chrome asks for permission. Click Allow.

Steps:

1. Log in to the portal in Chrome.
2. Ask the agent: "save my e-distribucion session".
3. The agent reads the `sid` value with the Chrome DevTools MCP. It reads the
   `Cookie` header of a portal request.
4. The agent calls the tool `edist_save_session` with the value.
5. The tool writes `sesion.json`.

Check the session. Ask the agent for `edist_status`.

## Notes for all flows

- The `sid` cookie is HttpOnly. A web page cannot read it. Only the browser, an
  extension, or the DevTools can read it.
- Do not share `sesion.json`. It is your live session.
- When a command fails with an authentication error, get a new `sid`. The
  session expired.
- The `aura.token` refreshes on each call. You do not manage it.
