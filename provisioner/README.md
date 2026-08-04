# provisioner

Mojolicious/Perl phone provisioning server for the VLAN 402 lab
(`192.168.142.0/24`). Serves per-device boot configs and directory files
keyed by MAC address, backed by a MariaDB device registry.

## Layout

- `lib/Provisioner.pm` — app startup: config loading, DB connection,
  migrations, routes.
- `lib/Provisioner/Controller/Provision.pm` — MAC lookup, vendor dispatch,
  request logging.
- `templates/config/{yealink,polycom}.cfg.ep` — per-vendor boot config
  templates.
- `templates/yealink/directory.xml.ep` — Yealink phone-book directory.
- `migrations/provisioner.sql` — `devices` and `provisioning_requests`
  schema, applied automatically on startup via `Mojo::mysql`.
- `deploy/provisioner.service` — systemd unit running the app under
  Hypnotoad via `carton exec`.
- `deploy/nginx-provisioner.conf` — nginx reverse proxy bound to
  `192.168.142.91:80`, proxying to Hypnotoad on `127.0.0.1:3000`.

## Routes

- `GET /health` — status check.
- `GET /<mac>.cfg` — primary boot config; vendor is read from the `devices`
  row and picks the matching template.
- `GET /yealink/directory/<mac>.xml` — Yealink phone-book directory
  (404s if the device isn't registered as `yealink`).

## Setup

```
cpanm carton                       # if not already installed
carton install                     # installs deps into ./local

mysql -u root -e "
  CREATE DATABASE provisioner CHARACTER SET utf8mb4;
  CREATE USER 'provisioner'@'localhost' IDENTIFIED BY 'CHANGE_ME';
  GRANT ALL PRIVILEGES ON provisioner.* TO 'provisioner'@'localhost';
"

echo -n 'CHANGE_ME' > .db_password   # chmod 600, gitignored, never commit
chmod 600 .db_password
```

`provisioner.yml` holds non-secret DB connection info (host/port/db/user)
and the Hypnotoad listen config. The DB password comes from
`.db_password` or `$PROVISIONER_DB_PASSWORD` — it is intentionally not in
git.

Tables (`devices`, `provisioning_requests`) are created automatically on
first startup via the migration in `migrations/provisioner.sql`.

## Running

Dev (auto-reload):

```
PERL5LIB=local/lib/perl5 morbo -l http://127.0.0.1:3000 script/provisioner
```

Production (systemd + Hypnotoad):

```
sudo cp deploy/provisioner.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now provisioner.service

sudo cp deploy/nginx-provisioner.conf /etc/nginx/sites-available/provisioner
sudo ln -s /etc/nginx/sites-available/provisioner /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Hot code reload with zero dropped requests:

```
sudo systemctl reload provisioner.service
```

## Adding a device

```sql
INSERT INTO devices (mac, vendor, model, label, extension, display_name,
                      sip_server, sip_port, sip_user, sip_password)
VALUES ('001565abcdef', 'yealink', 'T46U', 'Front Desk', '1001',
        'Front Desk', '192.168.142.91', 5060, '1001', 'CHANGE_ME');
```

`vendor` must be `yealink` or `polycom` — that's what selects the config
template in `Provisioner::Controller::Provision`.
