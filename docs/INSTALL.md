# Install

This file explains how to install the tool and how to run it.

## Requirements

- Python 3.9 or newer.
- Internet access to the e-distribucion private area.
- Your own account.

The tool uses only the Python standard library. It needs no other package.

## Install the tool

Open a terminal in the folder of the project (the folder with
`pyproject.toml`) and run one of these commands:

```bash
pipx install .
```

```bash
pip install .
```

`pipx` puts the tool in its own place. Use it when you have `pipx`. Else use
`pip`.

The install gives you the command `edistribucion`.

## Check the install

```bash
edistribucion --help
```

## Run the report

```bash
edistribucion
```

This is the same as:

```bash
edistribucion report
```

Add `--json` for raw JSON:

```bash
edistribucion report --json
```

The tool writes the progress of each step to stderr. The report, or the JSON,
goes to stdout.

## Run without installing the tool

You can also run the file:

```bash
python edistribucion.py report
```

## The first run (the session)

The tool needs a session. Run this command one time:

```bash
edistribucion login-backend --save
```

It asks for your NIF and your password. Then it writes `session.json`. The
`--save` also stores the password, encrypted with the Windows DPAPI, in
`credentials.json`.

See [AUTHENTICATION.md](AUTHENTICATION.md) for the other ways to get a session.

## Where the tool keeps the files

The tool looks for `session.json` and `credentials.json` in this order:

1. the folder of the file,
2. the current folder,
3. the user config folder:
   - Windows: `%APPDATA%\edistribucion`
   - Linux and macOS: `~/.config/edistribucion`

The tool writes a new file in the first place that already has one. If no place
has one, it writes in the user config folder.

So an installed tool works from any folder.

## Update the tool

After a change in the code, install again:

```bash
pip install --force-reinstall .
```

## Remove the tool

```bash
pip uninstall edistribucion-client
```

The files in the user config folder stay. Delete them by hand if you want.
