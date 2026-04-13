# Deployment Notes For `qc.jrti.org`

These files assume the same general server profile currently visible on `jrti.org`:

- Ubuntu
- `nginx`
- a local application process behind reverse proxy

## 1. DNS

Create a record for `qc.jrti.org` pointing at the server that will run this app.

- If it is the same machine as `jrti.org`, point `qc.jrti.org` to that host.
- If it is a different machine, point it to the new host instead.

## 2. App Install

Example layout:

```bash
sudo mkdir -p /opt/pq-agile-chain /var/lib/pq-agile-chain
sudo chown -R "$USER":www-data /opt/pq-agile-chain /var/lib/pq-agile-chain
git clone https://github.com/jbaelaw/pq-agile-chain.git /opt/pq-agile-chain
cd /opt/pq-agile-chain
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## 3. systemd

```bash
sudo cp deploy/systemd/pq-agile-chain.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pq-agile-chain.service
```

The service binds only to `127.0.0.1:8401`.

## 4. nginx

```bash
sudo cp deploy/nginx/qc.jrti.org.conf /etc/nginx/sites-available/qc.jrti.org.conf
sudo ln -s /etc/nginx/sites-available/qc.jrti.org.conf /etc/nginx/sites-enabled/qc.jrti.org.conf
sudo nginx -t
sudo systemctl reload nginx
```

## 5. TLS

After DNS resolves, issue a certificate:

```bash
sudo certbot --nginx -d qc.jrti.org
```

## 6. Smoke Check

```bash
curl http://127.0.0.1:8401/api/health
curl https://qc.jrti.org/api/health
```
