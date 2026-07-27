"""Standalone helper script: prints this machine's local IANA timezone name.

Not imported by the app itself — run manually (`python get_local_timezone.py`)
to get the value that belongs on the first line of `date_id.txt`, which
`Database.__init__` reads to determine "today" for the daily rollover.
"""

import tzlocal

# Get the local IANA timezone name from your OS
local_iana_name = tzlocal.get_localzone_name()

print(local_iana_name)