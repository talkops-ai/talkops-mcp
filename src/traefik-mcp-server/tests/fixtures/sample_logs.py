"""Sample Traefik JSON/CLF access logs and controller logs for testing."""

from typing import List


SAMPLE_ACCESS_LOG_LINES: List[str] = [
    '{"ClientHost":"10.1.2.3","RequestMethod":"GET","RequestPath":"/payments/checkout?token=topsecret123","DownstreamStatus":200,"Duration":15000000,"RouterName":"default-payments-route-0@kubernetescrd","ServiceName":"default-payments-wrr@kubernetescrd","request_Authorization":"Bearer jwt-secret-val"}',
    '{"ClientHost":"10.1.2.4","RequestMethod":"POST","RequestPath":"/payments/charge","DownstreamStatus":502,"Duration":180000000,"RouterName":"default-payments-route-0@kubernetescrd","ServiceName":"default-payments-wrr@kubernetescrd"}',
    '{"ClientHost":"10.1.2.5","RequestMethod":"GET","RequestPath":"/payments/status","DownstreamStatus":429,"Duration":1000000,"RouterName":"default-payments-route-0@kubernetescrd","ServiceName":"default-payments-wrr@kubernetescrd"}',
    '192.168.1.50 - - [04/Nov/2026:10:00:00 +0000] "GET /payments/list?api_key=abc999 HTTP/1.1" 200 512 "-" "Mozilla/5.0" 42 "default-payments-route-0@kubernetescrd" "http://10.244.0.10:8080" 12ms',
]

SAMPLE_CONTROLLER_LOG_LINES: List[str] = [
    '{"level":"error","providerName":"kubernetescrd","routerName":"default-broken-route@kubernetescrd","message":"middleware \\"default-missing-mw@kubernetescrd\\" does not exist","time":"2026-11-04T10:01:00Z"}',
    '{"level":"warn","providerName":"kubernetescrd","message":"TLS secret default/missing-tls not found","time":"2026-11-04T10:02:00Z"}',
    '2026-11-04T10:03:00Z INF Configuration reloaded from provider kubernetescrd',
]
