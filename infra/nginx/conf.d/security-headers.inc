# The security headers, in ONE place (WO-42 · LACTEVA-SECURITY-001).
#
# `.inc`, not `.conf`: nginx.conf includes `conf.d/*.conf`, so a file named
# `.conf` here would be loaded as a second server context. This is included
# explicitly, by the blocks that need it.
#
# WHY A SNIPPET AND NOT FIVE LINES IN THE SERVER BLOCK. They WERE five lines
# in the server block, and they were not reaching the browser. nginx's
# `add_header` directives "are inherited from the previous configuration level
# if and only if there are no add_header directives defined on the current
# level" — so `location /`, which adds its own `Cache-Control`, silently
# dropped every one of them. `curl -I https://dev.phoenixsoft.in/login`
# returned no HSTS, no X-Frame-Options and no nosniff on the deployed
# platform: configured, committed, reviewed, and not served.
#
# Anything that adds a header of its own must include this file too, and a
# test asserts that every such location does.
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
