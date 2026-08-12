# infra/

Infrastructure as code for the Lacteva platform: cloud resources, Kubernetes manifests, environment definitions, and delivery pipelines.

Empty during the documentation-foundation phase. The cloud provider, IaC tooling, and environment topology are platform ADRs to be authored in [`docs/03-architecture/adr/`](../docs/03-architecture/adr/README.md) before anything lands here.

## Rules (binding once code lands)

- All infrastructure is declared in code and applied through pipelines — no console-clicked resources; anything created manually during an incident is reconciled into code within 5 business days.
- Environments follow the naming in [STD-0002](../docs/00-standards/STD-0002-naming-conventions.md) (resource names carry environment suffixes).
- Secrets never appear in this folder in any form; reference the secrets manager.
- Changes affecting availability, cost profile, or tenant isolation require an ADR or an update to the relevant one.

## GitHub Actions → ECR (DEMO-010)

Images are built by `.github/workflows/images.yml` and pushed to the two
existing ECR repositories. The serving EC2 only pulls. Nothing about it
recurs in cost: GitHub's runners, repositories that already existed, free
intra-region pulls, and IAM.

No AWS key is stored in GitHub. The runner exchanges its OIDC token for a
session on `lacteva-github-actions-ecr`.

**The subject to trust is not the documented one.** This organization has
GitHub's immutable identifiers enabled, so the token's `sub` carries numeric
owner and repository IDs:

```
repo:valorantstech@164855793/lacteva@1319582534:ref:refs/heads/main
```

The trust policy matches that form, restricted to branches and tags — never
`pull_request`, which must not be able to publish an image, and which matters
because this repository is public. If `AssumeRoleWithWebIdentity` is ever
refused again, CloudTrail carries the offered subject and job logs do not:

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRoleWithWebIdentity
```

An ECR lifecycle policy keeps the 15 most recent images per repository, which
is generous on purpose — `deploy.sh --rollback` needs the previous release.
