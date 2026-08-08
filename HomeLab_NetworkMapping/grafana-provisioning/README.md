# Grafana Provisioning — TimsabLab Homelab

Config-as-code for the Grafana instance on monitoring01 (192.168.99.21).

## Layout

```
datasources/       - Prometheus + Loki datasource definitions
dashboards/
  dashboards.yaml   - provider config (foldersFromFilesStructure: true)
  Network/          - SNMP interfaces, Node Exporter Full
  Wireless/         - UniFi AP dashboard
  Virtualization/   - Proxmox VMs dashboard
  Servers/          - Servers overview (Node Exporter)
  Home/             - Landing page / home dashboard
```

The subfolder names under `dashboards/` map directly to Grafana folder names via `foldersFromFilesStructure: true` — adding a new subfolder here creates a new Grafana folder automatically.

## Deploying on monitoring01

This repo is cloned to `/etc/grafana/homelab-dashboards` on the server, and Grafana's
provisioning configs point at it directly:

- `/etc/grafana/provisioning/datasources/*.yaml` — copies of `datasources/*.yaml` here
- `/etc/grafana/provisioning/dashboards/dashboards.yaml` — copy of `dashboards/dashboards.yaml` here (points `path` at `/etc/grafana/homelab-dashboards`)

To pull in changes made here:

```bash
cd /etc/grafana/homelab-dashboards
sudo git pull
```

Grafana re-scans the dashboards directory every 30s (`updateIntervalSeconds`), so changes
show up automatically — no restart needed for dashboard JSON changes. Datasource changes
do require a `sudo systemctl restart grafana-server`.

## Not covered by provisioning

Grafana has no file-provisioning support for these — they stay database-only,
managed via the UI or the API:

- Alert rules (5 rules: SNMP device down, Proxmox down, UniFi poller down, disk/CPU thresholds)
- The "Homelab NOC Rotation" playlist
- The "Service Up/Down Status" library panel
- Snapshots
