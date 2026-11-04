#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 13 — prove both sites run the SAME artifact.
#
# Not a Jenkins stage — this is the evidence that ties the demo together.
# The PROD site and the DR site are different machines, but they load the
# same tarball, so their image ID and digest MUST be identical. That is
# what makes the failover meaningful: the same bytes, a different answer.
#
#   ./manual/step-13-show-same-artifact.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 13 — the same artifact on both sites"
step_start 13 "comparing the image ID and digest on PROD and DR"

state_load
require_state FULL_IMAGE

ensure_ansible_on_path

cd "${WORKDIR}/ansible"
export ANSIBLE_PRIVATE_KEY_FILE="${HOME}/.ssh/id_rhai108_rsa"

# `podman image inspect` writes JSON, so no Go-template braces are involved
# and Ansible's own templating never sees them.
ansible -i inventory.ini mcp_sites -m command \
    -a "podman image inspect $(local_ref "${FULL_IMAGE}")" \
    -o > "${REPORT_DIR}/image-inspect.json"

cd "${WORKDIR}"

python3 - "${REPORT_DIR}/image-inspect.json" "${PROD_HOST}" "${DR_HOST}" <<'PY'
import json
import sys

path, prod_host, dr_host = sys.argv[1], sys.argv[2], sys.argv[3]

with open(path, encoding="utf-8") as fh:
    data = json.load(fh)

seen = {}
for host, result in data.items():
    if result.get("failed"):
        raise SystemExit("FAIL: podman image inspect failed on %s: %s"
                         % (host, result.get("stderr", "")))
    entry = json.loads(result["stdout"])[0]
    seen[host] = (entry["Id"], entry.get("Digest", ""))

print()
print("  %-18s %-14s %s" % ("site", "image id", "digest"))
print("  %-18s %-14s %s" % ("-" * 18, "-" * 14, "-" * 40))
for host in (prod_host, dr_host):
    if host in seen:
        img_id, digest = seen[host]
        print("  %-18s %-14s %s" % (host, img_id[:12], digest))
print()

ids = {h: v[0] for h, v in seen.items()}
if prod_host in ids and dr_host in ids:
    if ids[prod_host] == ids[dr_host]:
        print("PASS: both sites run the SAME image (%s)" % ids[prod_host][:12])
    else:
        raise SystemExit("FAIL: the sites run DIFFERENT images: %s vs %s"
                         % (ids[prod_host], ids[dr_host]))
else:
    raise SystemExit("FAIL: did not get an image id for both sites")
PY

step_end 13
echo ""
note "the drill is over. PROD is live, DR is stopped — the intended DR posture."
note "the transcript of the whole drill is in ${TRANSCRIPT}"
