# The API's headers: the shared set, plus the policy only an API can have.
#
# WO-46 moved Content-Security-Policy to the edge with the rest. The API
# returns data, never a document, so `default-src 'none'` is exactly right and
# nothing it serves needs to load, frame, or submit anything.
#
# This also TIGHTENS one live response. The application relaxed its CSP for
# the Swagger paths — `script-src 'unsafe-inline'` — and `/openapi.json` is
# served in production (`/docs` itself is not), so a production endpoint was
# carrying a policy written for a page that does not exist there. It is a JSON
# document; the strict policy is the correct one.
include /etc/nginx/conf.d/security-headers.inc;
add_header Content-Security-Policy "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'" always;
