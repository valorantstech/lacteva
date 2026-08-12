"""Print the identity a GitHub runner is about to present to AWS.

`sts:AssumeRoleWithWebIdentity` is refused when the token's `sub` does not
match the role's trust policy, and the refusal does not say what `sub` was
offered — so the first failure of `images.yml` gave nothing to act on and
every hypothesis cost a push. This prints the claim.

Only `sub`, `aud`, `repository` and `ref` are printed. None is a secret: they
are the repository name and the git ref, both public in this repository. The
TOKEN is never printed, and this script is deliberately the only thing that
ever reads it.

    python3 .github/workflows/show-oidc-claims.py /tmp/oidc.json
"""

import base64
import json
import sys

SAFE = ("sub", "aud", "repository", "ref", "workflow_ref")


def main() -> int:
    body = json.load(open(sys.argv[1]))
    token = body.get("value")
    if not token:
        print("no token in the response — is `id-token: write` granted?", file=sys.stderr)
        print(json.dumps({k: v for k, v in body.items() if k != "value"}), file=sys.stderr)
        return 1
    # A JWT is header.payload.signature, base64url without padding.
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    for key in SAFE:
        print(f"{key}: {claims.get(key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
