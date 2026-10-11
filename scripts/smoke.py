"""Exercise a running stack through HTTP, including real inference and Mailpit.

This creates a disposable test account and scan. Run against test environments.
"""

import argparse
import html
import json
import re
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
from uuid import uuid4


class Browser:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(self, path, data=None, content_type=None):
        request = Request(self.base_url + path, data=data)
        if content_type:
            request.add_header("Content-Type", content_type)
        with self.opener.open(request, timeout=180) as response:
            return response.geturl(), response.read().decode()

    def csrf(self, path):
        _, page = self.request(path)
        match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page)
        if not match:
            raise RuntimeError(f"No CSRF token on {path}")
        return html.unescape(match.group(1))

    def post(self, path, values):
        return self.request(path, urlencode(values).encode(), "application/x-www-form-urlencoded")


def run(base_url, image, mail_url=None):
    browser = Browser(base_url)
    suffix = uuid4().hex[:10]
    email = f"smoke-{suffix}@example.com"
    password = "smoke-test-password-123"
    _, page = browser.request("/health/ready")
    assert json.loads(page)["status"] == "ok"
    location, _ = browser.post(
        "/register",
        {
            "csrf_token": browser.csrf("/register"),
            "username": f"smoke-{suffix}",
            "email": email,
            "password": password,
            "confirm_password": password,
        },
    )
    assert location.endswith("/login"), "Registration failed"
    location, _ = browser.post(
        "/login", {"csrf_token": browser.csrf("/login"), "email": email, "password": password}
    )
    assert location.endswith("/scanner"), "Login failed"
    boundary = uuid4().hex
    token = browser.csrf("/scanner")
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="csrf_token"\r\n\r\n{token}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="imageFile"; filename="sample.jpeg"\r\n'
            "Content-Type: image/jpeg\r\n\r\n"
        ).encode()
        + image.read_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    location, page = browser.request("/scanner", body, f"multipart/form-data; boundary={boundary}")
    assert "/scans/" in location and "Model score" in page, "Real scan failed"
    _, history = browser.request("/account")
    assert "View scan" in history, "Scan history missing"
    if mail_url:
        browser.post("/logout", {"csrf_token": browser.csrf("/account")})
        browser.post(
            "/reset_password", {"csrf_token": browser.csrf("/reset_password"), "email": email}
        )
        with urlopen(mail_url.rstrip("/") + "/api/v1/messages", timeout=10) as response:
            messages = json.load(response)["messages"]
        message = next(
            message
            for message in messages
            if any(recipient["Address"] == email for recipient in message["To"])
        )
        with urlopen(
            mail_url.rstrip("/") + "/api/v1/message/" + message["ID"], timeout=10
        ) as response:
            content = json.load(response)["Text"]
        reset_path = re.search(r"/reset_password/[^\s]+", content).group(0)
        new_password = "smoke-test-new-password-456"
        location, _ = browser.post(
            reset_path,
            {
                "csrf_token": browser.csrf(reset_path),
                "password": new_password,
                "confirm_password": new_password,
            },
        )
        assert location.endswith("/login"), "Reset failed"
        location, _ = browser.post(
            "/login",
            {"csrf_token": browser.csrf("/login"), "email": email, "password": new_password},
        )
        assert location.endswith("/scanner"), "Login with reset password failed"
    print(
        "HTTP smoke test passed: registration, login, real scan, history"
        + (", email and password reset." if mail_url else ".")
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--image", type=Path, default=Path("app/static/sample test images/NORMAL/IM-0001-0001.jpeg")
    )
    parser.add_argument("--mail-url", help="Mailpit web/API URL, such as http://localhost:8025")
    args = parser.parse_args()
    run(args.base_url, args.image, args.mail_url)
