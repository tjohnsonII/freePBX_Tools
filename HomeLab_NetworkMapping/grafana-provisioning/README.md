# Grafana Provisioning — TimsabLab Homelab

Config-as-code for the Grafana instance on monitoring01 (192.168.99.21).

## Layout

```
datasources/       - Prometheus + Loki datasource definitions (classic file provisioning)
dashboards/
  Network/          - SNMP interfaces, Node Exporter Full
  Wireless/         - UniFi AP dashboard
  Virtualization/   - Proxmox VMs dashboard
  Servers/          - Servers overview (Node Exporter)
  Home/             - Landing page / home dashboard
```

Each subfolder under `dashboards/` becomes its own top-level Grafana folder.

## How this syncs to Grafana

**Dashboards** sync via Grafana's native Git Sync feature (Administration → General →
Provisioning), not classic file provisioning:

- **Connection**: `TimsabLab Sync` — a GitHub App (`timsablab-grafana-sync`, App ID
  `4524523`) installed on this repo only, with Contents/Pull requests/Webhooks all
  set to Read & write
- **Repository**: `TimsabLab Homelab Grafana` — points at
  `HomeLab_NetworkMapping/grafana-provisioning/dashboards` on `main`, syncs every
  10s, and has a live webhook registered so pushes trigger an immediate sync
  (no waiting on the poll interval)
- **Workflow**: `write` — this is bidirectional. Editing a dashboard in Grafana's UI
  writes the change back to this repo, not just the other way around

**Datasources** (Prometheus, Loki) still use classic file provisioning — Grafana's
Git Sync app doesn't manage datasources, only dashboards/folders. Those are cloned
to `/etc/grafana/homelab-dashboards` on the server and read via
`/etc/grafana/provisioning/datasources/*.yaml`. To pull datasource changes:

```bash
cd /etc/grafana/homelab-dashboards
sudo git pull
sudo systemctl restart grafana-server   # required for datasource changes
```

## Important: don't delete dashboards via the Grafana API/UI while `write` is enabled

Because the workflow is bidirectional, deleting a dashboard in Grafana propagates
that deletion back to this repo — it will remove the file on the next sync. If you
want to remove a dashboard, delete the JSON file here and push instead of deleting
it in Grafana.

## Not covered by provisioning

Neither classic file provisioning nor Git Sync supports these — they stay
database-only, managed via the UI or the API:

- Alert rules (5 rules: SNMP device down, Proxmox down, UniFi poller down, disk/CPU thresholds)
- The "Homelab NOC Rotation" playlist
- The "Service Up/Down Status" library panel
- Snapshots
