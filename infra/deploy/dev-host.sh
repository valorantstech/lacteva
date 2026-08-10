#!/usr/bin/env bash
# Start and stop the development/demo host (COST-001).
#
#   ./infra/deploy/dev-host.sh stop     # ~$0.085/hour stops billing
#   ./infra/deploy/dev-host.sh start    # back in ~60s, same IP
#   ./infra/deploy/dev-host.sh status
#
# This environment has no customers, no SLA and no availability requirement,
# so the cheapest correct posture is "off unless somebody is using it".
# Stopping the instance stops the COMPUTE charge — about 80% of the bill.
#
# What KEEPS billing while stopped, and why it is worth it:
#   * EBS (~$8.21/month for 40 GB root + 50 GB data) — this is the machine.
#     Deleting it means rebuilding, which costs more in time than it saves.
#   * The Elastic IP (~$3.65/month) — AWS bills every public IPv4 since
#     February 2024, attached or not. Keeping it means the demo URL and the
#     TLS certificate stay valid across a stop/start. Release it (see below)
#     if the address does not need to survive.
#
# Docker's `restart: unless-stopped` brings the stack back on boot — but ONLY
# if the containers were left running when the host went down. `unless-stopped`
# means exactly what it says: a container someone stopped by hand stays stopped
# across a reboot, deliberately. So `stop` below powers the host off and leaves
# the containers in the running state, and `start` needs no deployment step.
#
# If you ever run `docker compose stop` yourself before shutting down, the
# stack will NOT come back on its own — bring it up with:
#   docker compose -f docker-compose.production.yml --env-file /etc/lacteva/.env.production up -d

set -euo pipefail

PROFILE="${AWS_PROFILE:-ibs}"
REGION="${AWS_REGION:-ap-south-1}"
NAME="${INSTANCE_NAME:-lacteva-production}"

id() {
  aws --profile "${PROFILE}" --region "${REGION}" ec2 describe-instances \
    --filters "Name=tag:Name,Values=${NAME}" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
    --query 'Reservations[0].Instances[0].InstanceId' --output text
}

INSTANCE="$(id)"
[ "${INSTANCE}" != "None" ] && [ -n "${INSTANCE}" ] || { echo "no instance tagged ${NAME} in ${REGION}"; exit 1; }

case "${1:-status}" in
  stop)
    aws --profile "${PROFILE}" --region "${REGION}" ec2 stop-instances --instance-ids "${INSTANCE}" \
      --query 'StoppingInstances[0].CurrentState.Name' --output text
    echo "stopping ${INSTANCE} — compute billing ends when it reaches 'stopped'"
    echo "containers are left in the running state, so they come back on start"
    ;;
  start)
    aws --profile "${PROFILE}" --region "${REGION}" ec2 start-instances --instance-ids "${INSTANCE}" \
      --query 'StartingInstances[0].CurrentState.Name' --output text
    echo "starting ${INSTANCE} — the compose stack restarts itself; give it ~60s"
    ;;
  status)
    aws --profile "${PROFILE}" --region "${REGION}" ec2 describe-instances --instance-ids "${INSTANCE}" \
      --query 'Reservations[0].Instances[0].{id:InstanceId,type:InstanceType,state:State.Name,ip:PublicIpAddress}' \
      --output table
    ;;
  *)
    echo "usage: $0 {start|stop|status}" >&2
    exit 2
    ;;
esac
