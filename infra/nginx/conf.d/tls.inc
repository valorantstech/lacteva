# The TLS terminus, in ONE place (WO-63).
#
# Four named server blocks now terminate TLS instead of one catch-all, and
# a cipher list or a protocol floor copied four times is a cipher list that
# will eventually differ on one hostname. The certificate is the same file
# for all of them: a single Let's Encrypt certificate carrying the four
# lacteva.com names (`lacteva.com`, `www`, `app`, `api`).

    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;   # TLS 1.3 chooses better than we do
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    ssl_stapling on;
    ssl_stapling_verify on;

    # --- security headers -------------------------------------------------
    # The API sets its own (SEC-001, `core/http_security.py`); these cover the
    # responses nginx produces itself — redirects, 413s, 502s — which never
    # reach the application middleware. `always` is required or they are
    # omitted from exactly those error responses.
    #
    # HSTS is the one to be careful with: it is close to irreversible for the
    # max-age you choose, so it is off until TLS is genuinely permanent.
    include /etc/nginx/conf.d/security-headers.inc;
