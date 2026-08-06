# Terraform

Infrastructure for the Lacteva production environment (INF-001).

| Directory | Target | Status |
| --- | --- | --- |
| `hetzner/` | Hetzner Cloud | **Primary** |
| `aws/` | AWS | Optional abstraction, thin by design — see `aws/README.md` |

Both provision the same topology: one VM, one static IP, one data volume, one
firewall. Everything above the machine — `../cloud-init/lacteva.yaml`, the
filesystem standard, `../systemd/`, `../deploy/deploy.sh` — is shared
unchanged, which is what keeps the second target from becoming a second
product.

## Running it

```bash
cd hetzner
cp terraform.tfvars.example terraform.tfvars   # git-ignored
export HCLOUD_TOKEN=...                        # never written to a file

terraform init
terraform plan     # read it, especially the first time
terraform apply
```

Full sequence, including what happens after `apply`:
[INFRASTRUCTURE.md §Provisioning](../../INFRASTRUCTURE.md).

## State

Local by default. A remote backend is commented out in `hetzner/versions.tf`
and should be enabled before a second person touches this — two people with
two local state files will each plan to destroy what the other created.

## Not applied

Neither configuration has ever been run. There is no Terraform binary and no
cloud account in the environment where they were written; they were validated
structurally and by the tests in
`services/platform-core/tests/test_deployment.py`. **The first `terraform plan`
is a review step, not a formality.**
