# The platform API's locations (WO-63).
#
# Included by `api.lacteva.com`, which exists FOR these, and by
# `app.lacteva.com`, so that `/v1/` answers on the host somebody is already
# on rather than 404ing there.
#
# Nothing here changed when it moved out of `lacteva.conf`.

    # --- health and metrics ----------------------------------------------
    # Liveness and readiness are polled constantly. Excluding them from the
    # access log keeps the log about traffic rather than about polling.
    location ~ ^/health/(live|ready)$ {
        include /etc/nginx/conf.d/security-headers-api.inc;
        access_log off;
        proxy_pass http://lacteva_api;
        proxy_set_header Host $host;
    }

    # Prometheus scrapes over the internal network. Exposing it publicly would
    # publish tenant counts, queue depths and error rates to anyone.
    location = /metrics {
        include /etc/nginx/conf.d/security-headers-api.inc;
        allow 10.0.0.0/8;
        allow 172.16.0.0/12;
        allow 192.168.0.0/16;
        deny all;
        proxy_pass http://lacteva_api;
        proxy_set_header Host $host;
    }

    # --- static assets ----------------------------------------------------
    # The API's own static files (not the portal's — those are under
    # /_next/static/ above).
    location /static/ {
        proxy_pass http://lacteva_api;
        proxy_cache static;
        proxy_cache_valid 200 301 302 24h;
        proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
        proxy_cache_lock on;
        proxy_hide_header Cache-Control;
        add_header Cache-Control "public, max-age=31536000, immutable" always;
        include /etc/nginx/conf.d/security-headers-api.inc;
        add_header X-Cache-Status $upstream_cache_status;
    }

    # The API's own documentation surface stays on the API even though the
    # portal owns `/`. Exact matches, so `/docs` cannot shadow a portal route.
    location = /docs {
        include /etc/nginx/conf.d/security-headers-api.inc;
        proxy_pass http://lacteva_api;
        proxy_set_header Host $host;
    }
    location = /redoc {
        include /etc/nginx/conf.d/security-headers-api.inc;
        proxy_pass http://lacteva_api;
        proxy_set_header Host $host;
    }
    location = /openapi.json {
        include /etc/nginx/conf.d/security-headers-api.inc;
        proxy_pass http://lacteva_api;
        proxy_set_header Host $host;
    }

    # Never cache an API response: they are tenant-scoped, and a cache that
    # does not know that is a cross-tenant leak with extra steps.
    # Sign-in, refresh, password reset: the same proxying as /v1/, on the
    # tighter budget. A whole collection centre shares one address, so the
    # burst is sized for a shift starting at once, not for one handset.
    location /v1/auth/ {
        include /etc/nginx/conf.d/security-headers-api.inc;
        limit_req zone=auth burst=20 nodelay;
        limit_conn conn 50;
        proxy_pass http://lacteva_api;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID      $request_id_final;
        proxy_read_timeout 75s;
        proxy_no_cache 1;
        proxy_cache_bypass 1;
    }

    location /v1/ {
        include /etc/nginx/conf.d/security-headers-api.inc;
        limit_req zone=api burst=60 nodelay;
        proxy_pass http://lacteva_api;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID      $request_id_final;
        proxy_read_timeout 75s;
        proxy_no_cache 1;
        proxy_cache_bypass 1;
    }
