"""SSL certificate utilities for the web server."""

import os


# SSL certificate directory (expanded from ~)
SSL_CERT_DIR = os.path.expanduser("~/https")


def get_ssl_cert_paths():
    """
    Auto-detect SSL certificate and key files in ~/https directory.

    Returns:
        tuple: (cert_path, key_path) or (None, None) if not found
    """
    cert_path = None
    key_path = None

    if os.path.isdir(SSL_CERT_DIR):
        for filename in os.listdir(SSL_CERT_DIR):
            filepath = os.path.join(SSL_CERT_DIR, filename)
            if os.path.isfile(filepath):
                if filename.endswith(".crt") and cert_path is None:
                    cert_path = filepath
                elif filename.endswith(".key") and key_path is None:
                    key_path = filepath

    return cert_path, key_path


def check_ssl_certs():
    """Check if SSL certificate files exist.

    Returns:
        bool: True if both cert and key files exist
    """
    cert_path, key_path = get_ssl_cert_paths()
    return cert_path is not None and key_path is not None
