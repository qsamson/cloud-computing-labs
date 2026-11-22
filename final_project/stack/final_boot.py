from __future__ import annotations

import base64
import gzip


def _pack(text: str) -> str:
    data = gzip.compress(
        text.encode("utf-8"),
        compresslevel=9,
    )
    return base64.b64encode(data).decode("ascii")


def build_python_boot_script(
    service_name: str,
    app_js: str,
    package_json: str,
    environment: dict,
) -> str:
    env_text = "\n".join(
        f'{key}="{value}"'
        for key, value in environment.items()
    ) + "\n"

    unit = f"""[Unit]
Description=Weather Advisor {service_name}
After=network-online.target

[Service]
EnvironmentFile=/opt/app/app.env
WorkingDirectory=/opt/app
ExecStart=/usr/bin/node /opt/app/app.js
Restart=always
User=ec2-user

[Install]
WantedBy=multi-user.target
"""

    return f'''#!/usr/bin/env python3
import base64
import gzip
from pathlib import Path
import subprocess

def unpack(value):
    return gzip.decompress(base64.b64decode(value))

def run(args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True)

run(["dnf", "install", "-y", "nodejs"])

Path("/opt/app").mkdir(parents=True, exist_ok=True)

Path("/opt/app/app.js").write_bytes(
    unpack("{_pack(app_js)}")
)

Path("/opt/app/package.json").write_bytes(
    unpack("{_pack(package_json)}")
)

Path("/opt/app/app.env").write_bytes(
    unpack("{_pack(env_text)}")
)

Path("/etc/systemd/system/{service_name}.service").write_bytes(
    unpack("{_pack(unit)}")
)

run(["npm", "install", "--omit=dev"], cwd="/opt/app")
run(["chown", "-R", "ec2-user:ec2-user", "/opt/app"])
run(["systemctl", "daemon-reload"])
run(["systemctl", "enable", "{service_name}.service"])
run(["systemctl", "restart", "{service_name}.service"])
'''
