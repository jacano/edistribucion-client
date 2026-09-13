# Authentication

The session is the `sid` cookie. The tool needs that value. There are four ways
to give it. All of them write the file `sesion.json`.

## `login` (recommended)

This command opens the portal and reads the session from your running Chrome
with the DevTools Protocol. It uses your normal Chrome. You do not set any port
or flag, and no new browser opens. The DevTools Protocol sees HttpOnly cookies,
so no code injection is needed.

Turn on remote debugging one time in Chrome:

1. Open `chrome://inspect/#remote-debugging`.
2. Turn on Remote debugging.

Use:

1. Run the command.

```bash
python edistribucion.py login
```

2. The portal opens. Log in if needed.
3. If Chrome asks for permission, click Allow.
4. The tool reads the `sid` cookie and writes `sesion.json`.

Options:

- `--profile-dir PATH` points to another Chrome user data directory.
- `--timeout SECONDS` changes the wait. The default is 180.

How it works: Chrome writes `DevToolsActivePort` in its user data directory. The
tool reads that file, connects to Chrome, and calls `Storage.getCookies`.

## `login-backend`

This command logs in with the portal login call. No browser.

```bash
python edistribucion.py login-backend
```

It asks for the NIF and the password. Then it writes `sesion.json`.

Add `--save` to store the credentials:

```bash
python edistribucion.py login-backend --save
```

The credentials go to `credenciales.json`. The password is encrypted with the
Windows Data Protection API (DPAPI). Only your Windows user can decrypt it. The
file holds no clear password.

Auto login: when `credenciales.json` exists, any command that finds the session
expired logs in again with the stored credentials. You see this line:

```
Stored session expired. Logged in again with the stored credentials.
```

To turn auto login off, delete `credenciales.json`.

## `import-cookies`

This command reads a `cookies.txt` file (the Netscape format) or a JSON export.
The browser extension "Get cookies.txt LOCALLY" writes that format. The tool
keeps only the cookies of the portal domain.

The tool finds the newest cookies file in your Downloads folder. You can also
give the path.

```bash
python edistribucion.py import-cookies
```

```bash
python edistribucion.py import-cookies cookies.txt
```

## `save`

This command stores a value that you already have. It is used by an agent or by
hand.

```bash
python edistribucion.py save --sid "<sid value>"
```

`--text` accepts a whole `Cookie` header, or a cURL line:

```bash
python edistribucion.py save --text "renderCtx=x; sid=00D...!AQEA...; oid=00D"
```

## Notes

- The `sid` cookie is HttpOnly. A web page cannot read it. The DevTools
  Protocol, an extension, or the portal itself can read it.
- Do not share `sesion.json` or `credenciales.json`.
- When the session expires, run `login` again, or let the auto login do it.
