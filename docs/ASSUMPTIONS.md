# Assumptions and limits

This file lists what can differ when you use the tool with another account. The
tool was built and tested with one real 2.0TD account.

## Scope

- The tool supports the 2.0TD tariff only, with three periods (P1, P2, P3).
- A supply with another tariff (3.0TD, 6.xTD) stops with an error and gives no
  report.

## Zone

- The tool detects the zone of each supply. The Peninsula, the Balearic Islands
  and the Canary Islands share one set of hours. Ceuta and Melilla share the
  other set, one hour later.
- The tool reads the postal code of the supply (51xxx is Ceuta, 52xxx is
  Melilla) and, when it is not there, the name of the city.
- When the portal gives no postal code and no city, the tool uses the hours of
  the Peninsula. Add `--zone ceuta-melilla` in that case.

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
- The report covers all the history by default. The tool asks for every contract
  version of the CUPS and every hour of consumption. A long history makes a
  large zip and a slower run. Use `--months N` to limit the report to the last
  N complete months.
- The tool deletes the zip file and its notification after the read. Use
  `--keep-artifacts` to keep both on the portal.
- The portal makes no notification when the role has the setting to stop the
  notifications. Then there is nothing to delete.

## Trace

- `--trace` writes every request, every response and every downloaded file to a
  folder, one folder for each run.
- The folder holds the session cookie and the token as they are. The tool masks
  only the user and the password of a `login` run.
- Keep the folder private. Do not put it in a public place.
