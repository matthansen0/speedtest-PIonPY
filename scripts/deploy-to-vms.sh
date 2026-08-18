#!/usr/bin/env bash
set -euo pipefail

if ! command -v az >/dev/null 2>&1; then
  echo "[error] Azure CLI is required before 'azd deploy' can copy the benchmark to the VMs." >&2
  exit 1
fi

if ! command -v azd >/dev/null 2>&1; then
  echo "[error] Azure Developer CLI is required to run the deployment flow." >&2
  exit 1
fi

if [[ -n "${AZURE_RESOURCE_GROUP:-}" ]] && [[ -n "${VM_ONE_NAME:-}" ]] && [[ -n "${VM_TWO_NAME:-}" ]]; then
  :
else
  ENV_FILE="${AZD_ENV_FILE:-}"
  if [[ -z "${ENV_FILE}" ]]; then
    ENV_FILE="$(find .azure -mindepth 2 -maxdepth 2 -name .env 2>/dev/null | head -n 1 || true)"
  fi

  if [[ -z "${ENV_FILE}" ]]; then
    echo "[error] No azd environment was found. Run 'azd env new' and then 'azd provision' before 'azd deploy'." >&2
    exit 1
  fi

  set -a
  # shellcheck disable=SC1090
  . "${ENV_FILE}"
  set +a
fi

RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-${resourceGroupName:-}}"
ADMIN_USERNAME="${ADMIN_USERNAME:-${VM_USER_NAME:-${vmUserName:-azureuser}}}"
VM_NAMES=("${VM_ONE_NAME:-${vmOneName:-}}" "${VM_TWO_NAME:-${vmTwoName:-}}")

if [[ -z "${RESOURCE_GROUP}" ]]; then
  echo "[error] AZURE_RESOURCE_GROUP was not found in the azd environment." >&2
  exit 1
fi

if [[ -z "${ADMIN_USERNAME}" ]]; then
  echo "[error] Could not determine the VM admin username from the azd environment." >&2
  exit 1
fi

for vm_name in "${VM_NAMES[@]}"; do
  if [[ -z "${vm_name}" ]]; then
    continue
  fi

  echo "[deploy] cloning the Pi-on-Py repo into /home/${ADMIN_USERNAME}/speedtest-PIonPY on ${vm_name}"
  az vm run-command invoke \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${vm_name}" \
    --command-id RunShellScript \
    --scripts "bash -lc 'set -e; apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git python3-venv python3-dev libgmp-dev libmpfr-dev libmpc-dev build-essential; install -d -o ${ADMIN_USERNAME} -g ${ADMIN_USERNAME} /home/${ADMIN_USERNAME}; if [ ! -d /home/${ADMIN_USERNAME}/speedtest-PIonPY/.git ]; then git clone https://github.com/matthansen0/speedtest-PIonPY /home/${ADMIN_USERNAME}/speedtest-PIonPY; fi; chown -R ${ADMIN_USERNAME}:${ADMIN_USERNAME} /home/${ADMIN_USERNAME}/speedtest-PIonPY; ls -ld /home/${ADMIN_USERNAME}/speedtest-PIonPY'" \
    --only-show-errors

done

echo "[deploy] benchmark repo is now available under /home/${ADMIN_USERNAME}/speedtest-PIonPY on both VMs"
echo "[deploy] connect through Azure Bastion to run: cd ~/speedtest-PIonPY && python3 prepare_benchmark.py"
