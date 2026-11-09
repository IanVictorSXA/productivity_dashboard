#!/bin/bash
#
# Chromium kiosk session for the productivity dashboard (Phase 3, group 9).
#
# Started by the desktop session's autostart -- see deploy/README.md for the
# one line that installs it. Two jobs, both of which exist because this machine
# has no keyboard attached:
#
#   1. Wait for the dashboard to actually answer before opening a browser at
#      it, rather than racing the containers and landing on an error page.
#   2. Relaunch Chromium if it ever exits, so a browser crash does not leave a
#      black screen that needs a human.
#
# Run `kiosk.sh --check` to see what it would launch, without launching it.

set -u

# Both services bind to 127.0.0.1 only (see docker-compose.yml), so these are
# always localhost; they are overridable for testing, not for deployment.
DASHBOARD_URL="${DASHBOARD_URL:-http://localhost:5173}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8080/api}"

# Its own profile directory: the kiosk must not inherit whatever tabs, prompts,
# or "restore pages?" state the user's normal Chromium was last left in.
PROFILE_DIR="${KIOSK_PROFILE_DIR:-$HOME/.config/dashboard-kiosk}"

POLL_SECONDS=2
RELAUNCH_SECONDS=5

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') kiosk: $*"
}

# `chromium` is the binary on Pi OS trixie (there is no `chromium-browser`);
# older images ship the other name, so accept either rather than break on a
# re-image.
find_chromium() {
    command -v chromium || command -v chromium-browser
}

answers() {
    curl -sfo /dev/null --max-time 5 "$1"
}

wait_for() {
    local url="$1" waited=0

    until answers "$url"; do
        sleep "$POLL_SECONDS"
        waited=$((waited + POLL_SECONDS))

        # One line a minute rather than one per poll: a cold boot after a
        # rebuild can genuinely take a while, and this log is meant to stay
        # readable.
        if [ $((waited % 60)) -eq 0 ]; then
            log "still waiting for $url (${waited}s)"
        fi
    done
}

chromium_arguments() {
    # --kiosk                          full screen, no tabs, no address bar
    # --noerrdialogs                   never block the screen with a modal
    # --disable-infobars               no "Chrome is being controlled..." strip
    # --disable-session-crashed-bubble a power cut must not leave a "restore
    #                                  pages?" prompt over the dashboard
    # --autoplay-policy=...            Phase 4 plays an alarm sound with no
    #                                  human gesture to authorize it; the flag
    #                                  goes on now, while the flags are here
    # --no-first-run                   no welcome flow on a fresh profile
    # --disable-features=TranslateUI   no translate bar over the UI
    # --password-store=basic           autologin never unlocks the system
    #                                  keyring (no login password is ever
    #                                  entered), so without this flag
    #                                  Chromium's first touch of its
    #                                  password manager / cookie-encryption
    #                                  key pops a blocking "unlock default
    #                                  keyring" dialog on every boot. This
    #                                  keeps that state in the profile dir
    #                                  instead of asking the OS keyring.
    printf '%s\n' \
        --kiosk \
        --noerrdialogs \
        --disable-infobars \
        --disable-session-crashed-bubble \
        --autoplay-policy=no-user-gesture-required \
        --no-first-run \
        --disable-features=TranslateUI \
        --password-store=basic \
        "--user-data-dir=$PROFILE_DIR" \
        "$DASHBOARD_URL"
}

check() {
    local browser status=0
    browser="$(find_chromium)" || {
        echo "no chromium binary on PATH (looked for chromium, chromium-browser)" >&2
        status=1
    }

    [ -n "$browser" ] && echo "browser:   $browser"

    for url in "$BACKEND_URL" "$DASHBOARD_URL"; do
        if answers "$url"; then
            echo "answering: $url"
        else
            echo "NOT ready: $url (the kiosk would wait here)"
            status=1
        fi
    done

    echo "profile:   $PROFILE_DIR"
    echo "would run: ${browser:-chromium} $(chromium_arguments | tr '\n' ' ')"

    return "$status"
}

main() {
    local browser
    browser="$(find_chromium)" || {
        log "no chromium binary on PATH — cannot start the kiosk"
        exit 1
    }

    log "waiting for the backend at $BACKEND_URL"
    wait_for "$BACKEND_URL"
    log "waiting for the dashboard at $DASHBOARD_URL"
    wait_for "$DASHBOARD_URL"

    mapfile -t arguments < <(chromium_arguments)

    while true; do
        log "launching $browser"
        "$browser" "${arguments[@]}"
        log "chromium exited ($?), relaunching in ${RELAUNCH_SECONDS}s"

        # Pause before relaunching so a Chromium that fails instantly cannot
        # spin, then re-check the dashboard: whatever killed the browser may
        # have taken the containers with it (a rebuild, a reboot in progress),
        # and reopening on an error page would defeat the point.
        sleep "$RELAUNCH_SECONDS"
        wait_for "$DASHBOARD_URL"
    done
}

case "${1:-}" in
    --check) check ;;
    "")      main ;;
    *)       echo "usage: $(basename "$0") [--check]" >&2; exit 2 ;;
esac
