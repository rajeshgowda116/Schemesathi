import socket
import ssl
import requests
import urllib3
from typing import Tuple, Dict, Optional
from urllib.parse import urlparse

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,application/pdf,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,kn;q=0.8',
}


def fetch_resource(url: str, timeout: int = 15) -> Tuple[int, bytes, str, str]:
    """
    Fetches a URL robustly, handling SSL/SNI issues common on govt servers.
    Returns: (status_code, content_bytes, content_type, final_url)
    """
    # 1. Try standard requests with SSL verify=False
    try:
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        resp = session.get(url, verify=False, timeout=timeout, allow_redirects=True)
        content_type = resp.headers.get('Content-Type', '')
        return resp.status_code, resp.content, content_type, resp.url
    except requests.exceptions.SSLError:
        pass
    except Exception as e:
        # If timeout or connection error, try fallback socket method below
        pass

    # 2. Fallback custom socket fetcher for SNI issues (e.g. www.karnataka.gov.in)
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme or 'https'
        host = parsed.hostname
        port = parsed.port or (443 if scheme == 'https' else 80)
        path = parsed.path or '/'
        if parsed.query:
            path += '?' + parsed.query

        if scheme == 'https':
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            # Try without 'www.' if host starts with 'www.'
            sni = host[4:] if host.startswith('www.') else host

            sock = socket.create_connection((host, port), timeout=timeout)
            try:
                ssock = ctx.wrap_socket(sock, server_hostname=sni)
            except Exception:
                sock = socket.create_connection((host, port), timeout=timeout)
                ssock = ctx.wrap_socket(sock, server_hostname=host)
        else:
            ssock = socket.create_connection((host, port), timeout=timeout)

        request_header = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: {DEFAULT_HEADERS['User-Agent']}\r\n"
            f"Accept: {DEFAULT_HEADERS['Accept']}\r\n"
            f"Connection: close\r\n\r\n"
        )
        ssock.sendall(request_header.encode('utf-8'))

        response_data = b""
        while True:
            chunk = ssock.recv(16384)
            if not chunk:
                break
            response_data += chunk
        ssock.close()

        # Parse HTTP response header & body
        header_end = response_data.find(b"\r\n\r\n")
        if header_end != -1:
            headers_raw = response_data[:header_end].decode('utf-8', errors='ignore')
            body = response_data[header_end + 4:]
            
            lines = headers_raw.split("\r\n")
            status_line = lines[0] if lines else ""
            status_code = 200
            if " " in status_line:
                try:
                    status_code = int(status_line.split(" ")[1])
                except ValueError:
                    status_code = 200

            content_type = ""
            for line in lines[1:]:
                if ":" in line:
                    key, val = line.split(":", 1)
                    if key.strip().lower() == "content-type":
                        content_type = val.strip()

            return status_code, body, content_type, url
        else:
            return 200, response_data, "", url

    except Exception as exc:
        raise RuntimeError(f"Failed to fetch URL {url}: {exc}")
