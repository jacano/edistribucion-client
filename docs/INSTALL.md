# Install

## Install the tool

From the folder of the project (the folder with `pyproject.toml`):

```bash
pipx install .        # recommended
```

```bash
pip install .         # or pip
```

The install gives the command `edistribucion`.

## First run (the session)

```bash
edistribucion login --save
```

It asks for your NIF and your password, and writes `session.json`. The `--save`
also keeps the password in the credential store of the system (DPAPI on
Windows, Keychain on macOS, libsecret on Linux). See
[AUTHENTICATION.md](AUTHENTICATION.md).

## File locations

The tool looks for `session.json` and `credentials.json` in this order:

1. the folder of the file,
2. the current folder,
3. the user config folder:
   - Windows: `%APPDATA%\edistribucion`
   - Linux and macOS: `~/.config/edistribucion`

So the installed tool works from any folder.

## Run without installing

```bash
python edistribucion.py report
```

## Update

```bash
pip install --force-reinstall .
```

## Remove

```bash
pip uninstall edistribucion-client
```

The files in the user config folder stay.
