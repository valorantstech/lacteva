# The admin portal's locations (WO-63).
#
# Included by every server block that SERVES the portal — today
# `app.lacteva.com` and `dev.phoenixsoft.in`. It exists as an include because
# the same locations now appear under more than one name, and two copies of a
# proxy configuration are two things that drift apart: the first time one of
# them gains a header the other does not, the difference is invisible until
# somebody reports it on one hostname only.
#
# Nothing here changed when it moved out of `lacteva.conf` — this is the
# configuration that was already deployed, given a name.

    # --- the admin portal -------------------------------------------------
    # `/` is the product a person opens. Every API path below is matched by a
    # more specific location, so this never swallows one.
    location / {
        limit_req zone=api burst=60 nodelay;
        limit_conn conn 50;

        proxy_pass http://lacteva_portal;
        proxy_http_version 1.1;

        # WebSocket upgrade. No endpoint uses it today; the platform's roadmap
        # has live collection monitoring, and discovering this is missing
        # during that work order is more expensive than four lines now.
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # Correlation id in, so the API binds the same one nginx logged.
        proxy_set_header X-Request-ID      $request_id_final;

        proxy_connect_timeout 5s;
        proxy_send_timeout    60s;
        # Longer than the API's own 30s statement timeout, so a slow request
        # is ended by the application (which logs why) rather than by nginx
        # (which only knows that it waited).
        proxy_read_timeout    75s;

        proxy_buffering on;
        proxy_buffers 16 16k;
        proxy_busy_buffers_size 32k;
        # Bulk import posts a whole file; buffering the request body to disk
        # first means a slow client cannot hold a Python worker open.
        proxy_request_buffering on;

        # A DEPLOY MUST REACH AN OPEN BROWSER (DEMO-010).
        #
        # Next sends `Cache-Control: s-maxage=31536000` for prerendered pages
        # and nothing a browser is required to honour — no `max-age`, no
        # `no-cache`. A browser is then free to apply heuristic freshness and
        # keep serving the PREVIOUS release's shell, which references the
        # previous release's chunks, for as long as it likes. That is how a
        # fix that is demonstrably live on the server is still not what the
        # person in front of it sees, and it makes every future portal fix
        # arrive at a time nobody can predict.
        #
        # `no-cache` does not mean "do not store": it means "store it, but
        # revalidate before reusing it". The ETag makes that a 304 in the
        # common case, so the cost is one conditional request per navigation
        # and the guarantee is that the shell is never older than the server.
        #
        # `/_next/static/` is a MORE SPECIFIC location and is unaffected —
        # those filenames are content-hashed, so they stay immutable for a
        # year. Only the document that names them is revalidated.
        #
        # `proxy_hide_header` first, because `add_header` APPENDS: without it
        # the response carries two Cache-Control values and the browser is
        # entitled to believe either.
        proxy_hide_header Cache-Control;
        add_header Cache-Control "no-cache" always;
        # Re-stated: this location's own add_header would otherwise drop
        # every inherited security header. See security-headers.inc.
        include /etc/nginx/conf.d/security-headers.inc;
    }

    # Next.js build output is content-hashed, so it is immutable and can be
    # cached hard. Served from the portal, not the API.
    location /_next/static/ {
        proxy_pass http://lacteva_portal;
        proxy_cache static;
        proxy_cache_valid 200 24h;
        proxy_cache_lock on;
        # Hide first: `add_header` appends, so without this the response
        # carries the upstream's Cache-Control as well as ours.
        proxy_hide_header Cache-Control;
        add_header Cache-Control "public, max-age=31536000, immutable" always;
        include /etc/nginx/conf.d/security-headers.inc;
        add_header X-Cache-Status $upstream_cache_status;
    }
