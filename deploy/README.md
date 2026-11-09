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

**After any change to `backend/requirements.in`, `backend/requirements.txt`,
`frontend/package.json`, or `frontend/package-lock.json`, rebuild like this — all
three parts:**

```bash
docker compose build && docker compose down -v && sudo systemctl restart productivity-dashboard.service
```

This is a rule, not a suggestion, and the `down -v` in the middle is the part
that looks redundant and is not:

- **Why rebuild at all**: the `./backend` and `./frontend` bind mounts carry
  source but *not* installed packages, so a dependency added without a rebuild
  is present in the source and absent from the image. It surfaces as a crash
  loop on an import that plainly exists in the file you are looking at — that
  is exactly how `ModuleNotFoundError: No module named 'gspread'` happened
  during Phase 3. Boot does not rebuild for you; nothing does.
- **Why `down -v`**: `/app/node_modules` is an anonymous volume, and Docker
  only fills a volume from the image when the volume is *empty*. Compose
  carries anonymous volumes forward when it recreates a container, so
  `docker compose build` on its own updates the image and the container while
  leaving the old `node_modules` mounted over it — a frontend dependency change
  silently does nothing. `-v` deletes the volume along with the containers so
  the next start repopulates it from the new image. Verified behavior, not a
  precaution.
- **The cost is one slow start, on purpose**: repopulating the volume copies
  ~65k files and takes ~2.5 minutes. That is why it lives here, in a command
  you run at a keyboard after a dependency change, instead of on the boot path.
- **`-v` also removes named volumes** declared in `docker-compose.yml`. There
  are none today — `productivity.db` is a bind-mounted file, not a volume — but
  if that ever changes, this command has to change with it.

Both dependency lists are pinned and both are generated from a working
environment, so a rebuild installs what the last verified one installed rather
than whatever the registry offers today. **Never hand-edit
`backend/requirements.txt`** — edit `backend/requirements.in` (the declared
list), rebuild, run the tests and `python sheets.py --check` inside the new
image, then regenerate the pinned file from it; the header in each file spells
out the command.

If you only edited source (`.py`, `.tsx`, …), none of this applies: the bind
mounts and the dev servers' reloaders pick it up with no restart at all.

Stop via `systemctl`, not `docker compose down` — `unless-stopped` will not
resurrect containers you stopped by hand, but the unit will bring them straight
back the next time it starts, and the two views of "is it running" are easier to
reason about if only one of them is used.

Because `ExecStop` is `docker compose stop`, a stopped stack leaves both
containers listed as `Exited` in `docker ps -a` (the frontend exits 1 — Vite
does not handle SIGTERM cleanly; it is cosmetic). That is intentional: keeping
the containers is what makes the next start fast. `docker ps` without `-a` is
empty either way.

### Notes

- **Boot never builds, and never recreates containers.** Two separate fixes,
  both needed to get boot from ~3 minutes to ~1 second:
  - No build step in the unit. BuildKit sweeps its cache on its own schedule
    (60-day keep duration, 5.588GiB reserved floor), and `docker compose build`
    re-runs a step whenever the cache record is gone — it does *not* treat the
    existing image as a cache source. So a build on the boot path meant an
    untouched repo could still pay a full `npm ci` before the screen came up.
    The first run of the unit on 2026-07-28 took 4m51s for exactly that reason.
  - `ExecStop=docker compose stop` rather than `down`. This was the larger half,
    and it is not obvious: `down` removes the containers, orphaning the
    anonymous `/app/node_modules` volume, so the next `up` copies ~65k files
    (405MB) out of the image into a fresh one. Measured at 156–176s, on every
    boot, with nothing changed. It is file-count bound, not bandwidth bound —
    the same 405MB written sequentially takes 0.15s on this hardware.
- **A power cut is not the slow path.** When power is pulled, `ExecStop` never
  runs, so the containers survive and the Docker daemon's own `unless-stopped`
  restore brings them back in ~4s without the unit's help. Before the `stop`
  change, this meant yanking the cord recovered *faster* than a clean
  `sudo reboot`, which was the only path that ran `down`.
- **Orphaned volumes**: Docker never garbage-collects anonymous volumes, so
  every container removal leaks one (~180MB here) permanently. Keeping the
  containers is what stops the bleeding; `docker volume prune` is the mop for
  whatever still accumulates from `down -v` rebuilds. `docker system df` shows
  the damage — it had reached 1.486GB across 9 dead volumes before the Group 8b
  cleanup.
- **Build cache**: now that builds only happen when you run one, a cold cache
  costs you ~80s while you are sitting in front of it, not a blank kiosk at
  boot. `docker builder prune` on your own schedule is fine.
- **Container logs are capped** at 10MB × 3 files per service, set in
  `docker-compose.yml`. Docker's `json-file` driver does not rotate by default,
  and because `ExecStop` keeps the containers alive across restarts, nothing
  else ever truncates those files — the old `down` behavior used to delete them
  along with the container. Changing the `logging:` block needs a container
  recreation to take effect, which any `systemctl restart` does once the compose
  file has changed.
- **What still grows, and what does not**: dangling images do *not* accumulate
  here (the containerd snapshotter releases the old image when a rebuild
  retags), the journal self-rotates at ~4GB, and the build cache is
  BuildKit-GC'd. `docker system df` shows all four categories at once and is the
  one command worth running if the disk looks fuller than expected.
- **Environment**: compose reads `.env` from `WorkingDirectory`. The Sheets
  variables (`SHEETS_SYNC_ENABLED`, `SHEETS_KEY_FILE_HOST`,
  `SHEETS_SPREADSHEET_ID`, `SHEETS_TAB_NAME`) belong there — see `.env.example`
  at the repo root. Sync stays off, and the app boots normally, if `.env` is
  absent.
- **Ports**: both services bind to `127.0.0.1` only (5173 frontend, 8080
  backend). Nothing on the LAN can reach the dashboard, by design.

## Kiosk browser session

`kiosk.sh` waits for the dashboard to answer, opens Chromium full-screen at it,
and relaunches Chromium if it ever exits. The relaunch loop is the point: this
machine has no keyboard, so a browser crash would otherwise leave a black screen
until someone finds one.

What the device actually runs (checked 2026-08-18, not assumed — the answers
differ from older Pi images and change how this is installed):

- **Compositor: labwc**, on Wayland, Pi OS trixie. Not wayfire, not X11 — so
  `xset s off -dpms` and `~/.config/wayfire.ini` are both the wrong tool here.
- **Chromium is `/usr/bin/chromium`.** There is no `chromium-browser` on
  trixie; `kiosk.sh` accepts either name so a re-image onto an older release
  still works.
- **Autologin is already on**: `/etc/systemd/system/getty@tty1.service.d/autologin.conf`
  carries `--autologin team`, and the default target is `graphical.target`.
  The kiosk depends on this — no session, no autostart, no dashboard.

### Install

Append one line to the user's labwc autostart:

```bash
echo '/home/team/coding/productivity_dashboard/deploy/kiosk.sh >> ~/.cache/dashboard-kiosk.log 2>&1 &' >> ~/.config/labwc/autostart
```

Then log out and back in, or reboot.

**Why that file**: the session runs `labwc -m` (`labwc-pi` execs it), and `-m` is
*merge-config* — the user's `~/.config/labwc/autostart` is additive to
`/etc/xdg/labwc/autostart`, not a replacement for it. That is why the panel and
file manager keep running with a user autostart present, and it is the same file
`raspi-config` appends its screen-blanking line to.

**The alternative, if you prefer XDG autostart**: `/etc/xdg/labwc/autostart` ends
with `lxsession-xdg-autostart`, so a `~/.config/autostart/kiosk.desktop` is
launched too:

```bash
mkdir -p ~/.config/autostart && cp deploy/kiosk.desktop ~/.config/autostart/
```

**Install one or the other, never both** — two autostart entries means two
Chromiums fighting for the screen.

### Check it without rebooting

```bash
deploy/kiosk.sh --check    # prints the browser, whether each URL answers, and
                           # the exact command it would run. Launches nothing.
```

Exit 0 means it would start immediately; exit 1 means it would sit in its wait
loop, and the line naming the URL says what it is waiting for.

### The screen must not blank

A kiosk that blanks after ten minutes is a black screen with no keyboard to wake
it. On labwc this is a `swayidle` line in the same autostart file, added and
removed by `raspi-config`:

```bash
grep swayidle ~/.config/labwc/autostart   # no output = blanking is off (current state)
sudo raspi-config nonint do_blanking 1    # 1 disables, 0 enables — yes, that way round
```

Nothing in this repo touches it; it is already off on this device, and this is
the check to re-run after a re-image.

### "Unlock default keyring" prompt on every boot

This is autologin, not a bug in this repo's units: a normal desktop login
unlocks the keyring with the password you type at the greeter, and
`getty@tty1` autologin never types one, so the keyring stays locked and the
first thing that asks it for a secret — Chromium's password manager / cookie
encryption key, via `libsecret` — blocks on a dialog with no keyboard to
answer it. `kiosk.sh` passes `--password-store=basic`, which keeps that state
in Chromium's own profile dir instead of asking the OS keyring, so the prompt
never fires. Confirmed with `--check` (prints the flag in the command line);
a from-cold `sudo reboot` is the only way to confirm the dialog itself is
gone, since nothing here can safely drive the real screen.

### Day-to-day

```bash
tail -f ~/.cache/dashboard-kiosk.log   # what the kiosk is waiting for / relaunching
pkill -f dashboard-kiosk               # kill Chromium; the wrapper reopens it in ~5s
```

To stop the kiosk for good, delete the autostart line (or the `.desktop`) first,
then `pkill -f kiosk.sh` before killing Chromium — otherwise the wrapper is doing
exactly its job and putting the browser straight back.

Chromium runs against its own profile at `~/.config/dashboard-kiosk`, so the
kiosk never inherits the tabs or "restore pages?" state of a browser someone was
using by hand.
