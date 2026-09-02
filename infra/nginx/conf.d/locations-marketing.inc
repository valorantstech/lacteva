# The marketing site's locations (WO-63 · MARKETING-001).
#
# `lacteva.com` and `www.lacteva.com` only. The site is a separate Next.js
# server with no session, no API client and nothing tenant-scoped in it — it
# is deliberately NOT the same upstream as the portal, so a defect in the
# public website cannot reach a dairy's data and a deploy of one does not
# restart the other.
#
# `/privacy-policy` is the address the Play Console listing points at, so it
# has to be publicly reachable without a session forever; there is nothing
# special to configure for that beyond not putting a guard in front of it,
# and the E2E-facing check in the report proves it.

    location / {
        limit_req zone=api burst=60 nodelay;
        limit_conn conn 50;

        proxy_pass http://lacteva_marketing;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID      $request_id_final;

        proxy_connect_timeout 5s;
        proxy_send_timeout    60s;
        proxy_read_timeout    75s;

        proxy_buffering on;
        proxy_buffers 16 16k;

        # The same reasoning as the portal (DEMO-010): Next sends
        # `s-maxage` and nothing a browser must honour, so a browser may keep
        # serving the previous release's shell indefinitely. `no-cache` means
        # "revalidate", not "do not store" — the ETag makes it a 304.
        proxy_hide_header Cache-Control;
        add_header Cache-Control "no-cache" always;
        include /etc/nginx/conf.d/security-headers.inc;
    }

    # Content-hashed build output: immutable for a year, like the portal's.
    location /_next/static/ {
        proxy_pass http://lacteva_marketing;
        proxy_cache static;
        proxy_cache_valid 200 24h;
        proxy_cache_lock on;
        proxy_hide_header Cache-Control;
        add_header Cache-Control "public, max-age=31536000, immutable" always;
        include /etc/nginx/conf.d/security-headers.inc;
        add_header X-Cache-Status $upstream_cache_status;
    }
