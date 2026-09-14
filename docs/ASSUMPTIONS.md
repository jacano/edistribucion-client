# Assumptions and limits

This file lists what can differ when you use the tool with another account. The
tool was built and tested with one real 2.0TD account.

## Scope

- The tool supports the 2.0TD tariff only, with three periods (P1, P2, P3).
- A supply with another tariff (3.0TD, 6.xTD) stops with an error and gives no
  report.

## Zone

- The period hours are the ones of the Peninsula, Illes Balears and Canarias.
- Ceuta and Melilla use other hours, so the period split can be wrong there.

## Environment

- Python 3.9 or newer. The tool uses the standard library only.
- `--save` keeps the password in the credential store of the system: DPAPI on
  Windows, Keychain on macOS, libsecret on Linux.
- On Linux, `--save` needs the `secret-tool` tool (the `libsecret-tools`
  package).

## Reliability

- The tool depends on the portal. The portal can change the action names, the
  app version, the cookie names or the file format. Then the tool can stop.
- The portal makes the zip in the background. A large account can need more
  than the 3 minute wait.
