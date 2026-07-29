# Deploying on the Pi

Host configuration for the Raspberry Pi that runs the dashboard. Nothing here is
installed automatically — the files in this directory are copied into place by
hand, on the device, by the user.

Paths below assume the repo is at `/home/team/coding/productivity_dashboard`. If
it lives elsewhere, edit `WorkingDirectory` in
`productivity-dashboard.service` to match before installing.

## Services start on boot

Two independent layers, so neither a container crash nor a power cut needs a
human:

- `restart: unless-stopped` on both compose services — Docker brings a crashed
  or exited container back while the daemon is running.
- `productivity-dashboard.service` — a system-level systemd unit that runs
  `docker compose up` at boot, so the stack comes back after the machine itself
  goes down. `Restart=on-failure` covers compose exiting non-zero.

### Install

```bash
sudo cp deploy/productivity-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now productivity-dashboard.service
```

### Check it

```bash
systemctl status productivity-dashboard.service
curl -s 127.0.0.1:8080/api        # backend answers
curl -sI 127.0.0.1:5173           # frontend answers
```

Logs go to the journal, and the container logs stay where they always were:

```bash
journalctl -u productivity-dashboard.service -f
docker compose logs -f backend
```

### Day-to-day

```bash
sudo systemctl restart productivity-dashboard.service   # after pulling changes
sudo systemctl stop productivity-dashboard.service      # stop the stack
```

Stop via `systemctl`, not `docker compose down` — `unless-stopped` will not
resurrect containers you stopped by hand, but the unit will bring them straight
back the next time it starts, and the two views of "is it running" are easier to
reason about if only one of them is used.

### Notes

- **Rebuilds**: the unit runs `docker compose build` before `up`, so a change to
  `backend/requirements.txt` or `frontend/package.json` is picked up on the next
  restart. With a warm BuildKit cache this costs a couple of seconds. A failing
  build is deliberately non-fatal (the `-` prefix on `ExecStartPre`) — the
  dashboard comes up on the previous image instead of not coming up at all. If a
  dependency change seems not to have taken effect, check
  `journalctl -u productivity-dashboard.service` for the build output.
- **A cold build cache delays startup by minutes.** BuildKit garbage-collects
  its cache, and the frontend's `FROM node:22` + `npm install` are ~3 minutes on
  this hardware once those entries are gone (the first run of the unit on
  2026-07-28 took 4m51s to reach a listening container for exactly this reason;
  the next build took 1.4s). Startup blocks on it. Two things keep that from
  hurting: `restart: unless-stopped` means the Docker daemon brings the previous
  containers up on its own at boot, before the unit finishes building, and
  `docker system df` is worth a look if the cache has grown enough to be
  GC-pressured — `docker builder prune` on your own schedule is preferable to
  BuildKit doing it right before a reboot.
- **Environment**: compose reads `.env` from `WorkingDirectory`. The Sheets
  variables (`SHEETS_SYNC_ENABLED`, `SHEETS_KEY_FILE_HOST`,
  `SHEETS_SPREADSHEET_ID`, `SHEETS_TAB_NAME`) belong there — see `.env.example`
  at the repo root. Sync stays off, and the app boots normally, if `.env` is
  absent.
- **Ports**: both services bind to `127.0.0.1` only (5173 frontend, 8080
  backend). Nothing on the LAN can reach the dashboard, by design.
