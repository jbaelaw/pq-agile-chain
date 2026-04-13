# Deployment Notes For `jrti.org/qc`

These files assume the app will run on the same server that already serves `jrti.org`:

- Ubuntu
- `nginx`
- a local application process behind reverse proxy

## 1. App Install

Example layout:

```bash
sudo mkdir -p /opt/pq-agile-chain /var/lib/pq-agile-chain
sudo chown -R "$USER":www-data /opt/pq-agile-chain /var/lib/pq-agile-chain
git clone https://github.com/jbaelaw/pq-agile-chain.git /opt/pq-agile-chain
cd /opt/pq-agile-chain
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## 2. systemd

```bash
sudo cp deploy/systemd/pq-agile-chain.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pq-agile-chain.service
```

The service binds only to `127.0.0.1:8401`.

## 3. nginx

```bash
sudo cp deploy/nginx/jrti.org-qc.conf /etc/nginx/snippets/jrti.org-qc.conf
```

Then include the snippet inside the existing `server_name jrti.org` block:

```nginx
include /etc/nginx/snippets/jrti.org-qc.conf;
```

After that:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 4. Smoke Check

```bash
curl http://127.0.0.1:8401/api/health
curl https://jrti.org/qc/api/health
```
