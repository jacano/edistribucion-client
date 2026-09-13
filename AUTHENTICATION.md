# Authentication

The starting point is the tool. Run the `login` command. The tool opens the
e-distribucion login page. Log in to the portal. Then choose how to return the
session.

```bash
python edistribucion.py login
```

The tool shows three ways:

```
  paste    copy the Cookie header (or a cURL line) from DevTools and paste it here
  cookies  import a cookies.txt file
  agent    let the agent read it with the Chrome DevTools MCP

Type paste, cookies or agent [paste]:
```

You can pick the way in advance with `--method`:

```bash
python edistribucion.py login --method paste
```

All ways write `sesion.json`. The session is the `sid` cookie.

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

This option uses a browser extension. The extension can read the cookie store,
because Chrome trusts it. The tool cannot. So the extension writes the cookies
to a file, and the tool reads that file.

### Install the extension

One example is "Get cookies.txt LOCALLY":

`https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc`

1. Open the link in Chrome.
2. Click "Add to Chrome".
3. Click "Add extension" in the dialog.
4. Pin the extension. Click the puzzle piece icon, then the pin next to the
   extension name.

Any extension that exports the Netscape `cookies.txt` format works.

### Export the cookies

Do this after you log in, and only when the session expired.

1. Log in to the portal.
2. Click the extension icon.
3. Select the current site or the export option.
4. Select the Netscape format, if the extension asks.
5. Click "Export" or "Download". The file goes to your Downloads folder. The
   usual name is `cookies.txt`.

### Import the cookies

The tool finds the newest cookies file in your Downloads folder. You can also
type the path.

```bash
python edistribucion.py import-cookies
```

Or give the path:

```bash
python edistribucion.py import-cookies cookies.txt
```

The command copies the `sid` cookie into `sesion.json` and checks the session.
You can delete `cookies.txt` after that.

### Why an import is needed

The extension and the tool are two different programs. The extension writes a
file. The tool reads the file. The export alone is not enough, because the file
only sits in your Downloads folder. The import is the step that copies the file
into the tool session.

## Option 3: agent reads the session with the Chrome DevTools MCP

This option is for an agent. The agent uses the `chrome-devtools` MCP with
autoconnect. That MCP attaches to your normal Chrome. It does not change your
profile.

What you need:

- The `chrome-devtools` MCP with autoconnect. You configured it already.
- Remote debugging turned on one time.

Turn on remote debugging:

1. Open `chrome://inspect/#remote-debugging`.
2. Turn on Remote debugging.
3. When the agent connects, Chrome asks for permission. Click Allow.

Steps:

1. Log in to the portal in Chrome.
2. Ask the agent: "capture my e-distribucion session".
3. The agent reads the `Cookie` header of a portal request with the MCP.
4. The agent saves the session in one of two ways.

```bash
python edistribucion.py save --sid "<sid value>"
```

```bash
python edistribucion.py save --text "<Cookie header>"
```

5. The tool writes `sesion.json` and checks the session.

This option works because the MCP reads the request, not the page. The request
carries the HttpOnly `sid` cookie. The page cannot see it. The request can.

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

- The `sid` cookie is HttpOnly. A web page cannot read it. The DevTools or an
  extension can read it.
- Do not share `sesion.json`. It is your live session.
- When a command fails with an authentication error, run `login` again. The
  session expired.
- The `aura.token` refreshes on each call. You do not manage it.
