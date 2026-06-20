import tzlocal

# Get the local IANA timezone name from your OS
local_iana_name = tzlocal.get_localzone_name() 

print(local_iana_name)