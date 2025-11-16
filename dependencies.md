# Python dependencies

Top-level packages to install:
- PyQt5
- requests
- pandas
- Flask
- cryptography

Install with pip:
```bash
pip install PyQt5 requests pandas Flask cryptography
```

Notes:
- On Raspberry Pi, PyQt5 can also be installed via apt: `sudo apt install python3-pyqt5`.
- Installing Flask via pip pulls its transitive dependencies (Werkzeug, Jinja2, click, itsdangerous).
- The cryptography library is used for encrypting WiFi passwords. It requires system dependencies on some platforms.
- For WiFi functionality, NetworkManager (nmcli) should be available on Raspberry Pi OS, or wireless-tools (iwlist) as a fallback.


