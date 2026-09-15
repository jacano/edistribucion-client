# Authentication

The portal session is the `sid` cookie. The tool needs that value. There are
three ways to give it, and all of them write the file `session.json`.

The examples use `python edistribucion.py`. The installed tool is the same:
write `edistribucion` in place of `python edistribucion.py`.

The tool writes `session.json` and `credentials.json` in the folder of the
file, or in the current folder. If neither has the files, it uses the user
config folder (`%APPDATA%\edistribucion` on Windows, `~/.config/edistribucion`
on Linux and macOS).

## Which one to use

- `login`: you have your NIF and your password. This is the easy way.
- `import-cookies`: you are logged in in the browser and you want a cookie
  file. Use the browser extension below.
- `set-session`: you have the `sid` value. Use it for a script or an agent.

## `login`

This command logs in with the portal login call. No browser.

```bash
python edistribucion.py login
```

It uses the stored credentials if `credentials.json` exists. If not, it asks
for the NIF and the password. Then it writes `session.json`.

Add `--save` to store the credentials:

```bash
python edistribucion.py login --save
```

Without `--save`, the tool asks you if you want to save the credentials. It asks
only on a terminal. In a script (no terminal) it does not save and it does not
ask. Answer `y` or `yes` to save. Any other answer, or Enter, does not save.

The credentials go to `credentials.json`. The password is kept in the
credential store of the system:

- Windows: the Data Protection API (DPAPI). The file holds the encrypted value.
- macOS: the Keychain, with the `security` tool. The file holds the username.
- Linux: libsecret, with the `secret-tool` tool. The file holds the username.

Only your user can read the password. The file holds no clear password. On
Linux, install `libsecret-tools` (the `secret-tool` tool) to use `--save`.

Auto login: when `credentials.json` exists, any command that finds the session
expired logs in again with the stored credentials. You see this line:

```
Stored session expired. Logged in again with the stored credentials.
```

To turn auto login off, delete `credentials.json`.

How it works: the tool calls the portal login action. The response holds the
frontdoor URL with a pre-session. The tool follows the chain (frontdoor, login
flow, landing page, home). The home page then sets the `sid` cookie and the
`aura.token` cookie.

## `import-cookies`

This command reads a `cookies.txt` file (the Netscape format) or a JSON export.
It keeps only the cookies of the portal domain.

The tool finds the newest cookies file in your Downloads folder. You can also
give the path.

```bash
python edistribucion.py import-cookies
```

```bash
python edistribucion.py import-cookies cookies.txt
```

Export the file right before the import. Each new login can end the previous
session, so an old file may hold a dead session.

### The browser extension

The command reads the Netscape `cookies.txt` format. The extension **Get
cookies.txt LOCALLY** exports that format. It is open source.

- Chrome: <https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc>
- Firefox: <https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt-locally/>
- Source code: <https://github.com/kairi003/Get-cookies.txt-LOCALLY>

## `set-session`

This command stores a session value that you already have. It is used by an
agent or by hand.

### The `--sid` value

`--sid` takes the value of the `sid` cookie, not the name `sid=`. Use the exact
value, with no spaces.

```bash
python edistribucion.py set-session --sid "00D000000000ABC!AQEAQ...long text...9XyZ"
```

The value has two parts, joined by `!`:

1. a short id (15 characters). It is always the same for your account.
2. a long text with dots.

The quotes in the example are for the shell. Do not put quotes in the value.
A leading `sid=` is also accepted, so both forms work.

To get the value:

1. Log in to the portal in the browser.
2. Open the developer tools (F12) and the **Network** tab.
3. Open a request to `zonaprivada.edistribucion.com`.
4. In **Request Headers**, find the `Cookie` header.
5. Copy the text after `sid=` (up to the next `;`).

The browser cookie panel also shows the `sid` cookie for the portal domain.

### The `--text` value

`--text` takes a whole `Cookie` header, or a cURL line that holds one. The tool
keeps the cookies of the portal only.

```bash
python edistribucion.py set-session --text "sid=00D000000000ABC!AQEAQ...; oid=00D...; sid_Client=o00000...; inst=APP_cj"
```

The tool reads these names: `sid`, `oid`, `sid_Client`, `inst` and `clientSrc`.
Only `sid` is required. Each pair is `name=value`, and the pairs are joined by
`;`.

### The `--cookie` value

`--cookie` adds more cookies, as `name=value` pairs joined by `;`:

```bash
python edistribucion.py set-session --sid "00D...!..." --cookie "autocomplete=0; _gid=GA1.2..."
```

## Notes

- The `sid` cookie is HttpOnly. A web page cannot read it. The portal itself,
  or the browser cookie panel, can read it.
- Do not share `session.json` or `credentials.json`.
- When the session expires, run `login` again, or let the auto login do it.
