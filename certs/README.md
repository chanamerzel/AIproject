# certs/

Extra root certificates that the Docker image adds to its trust store.

Needed only on networks that intercept HTTPS (Israeli content filters such as Symen or NetFree,
corporate proxies). Generate on Windows with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\export_proxy_cert.ps1
```

`*.crt` files here are machine-specific and are not committed.
