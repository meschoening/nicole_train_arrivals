# Binding to port 80 without sudo (Raspberry Pi)

On Linux, binding to ports below 1024 requires special privileges. Grant the capability once to the Python interpreter used by this app.

1) Install capability tools:

```bash
sudo apt-get update && sudo apt-get install -y libcap2-bin
```

2) Find the Python binary used to run the app (system or your venv):

```bash
which python3
# or for a venv
readlink -f venv/bin/python
```

3) Grant low-port bind capability to that Python binary:

```bash
sudo setcap cap_net_bind_service=+ep /full/path/to/python3
```

Notes:
- Reapply after Python upgrades or if you switch venvs.
- No code changes required; the app will bind Flask on 0.0.0.0:80.
- To revoke: `sudo setcap -r /full/path/to/python3`.

