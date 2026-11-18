"""T-U3: Unit tests for per-language OTLP protocol and port alignment (B7 fix)."""

from __future__ import annotations

import json
from pathlib import Path

from opentelemetry_mcp_server.utils.k8s_labels import (
    CONTAINER_NAMES_ANNOTATION,
    DOTNET_RUNTIME_ANNOTATION,
    GO_TARGET_EXE_ANNOTATION,
    LANGUAGE_DEFAULT_OTLP,
    derive_language_otlp_env,
)


def test_python_and_dotnet_use_http_protobuf_port_4318():
    assert LANGUAGE_DEFAULT_OTLP["python"] == ("http/protobuf", 4318)
    assert LANGUAGE_DEFAULT_OTLP["dotnet"] == ("http/protobuf", 4318)

    py_env = derive_language_otlp_env("http://otel-col:4317", "python")
    assert py_env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://otel-col:4318"
    assert py_env["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/protobuf"

    dn_env = derive_language_otlp_env("http://otel-col:4317", "dotnet")
    assert dn_env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://otel-col:4318"
    assert dn_env["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/protobuf"


def test_java_and_nodejs_use_grpc_port_4317():
    for lang in ("java", "nodejs"):
        assert LANGUAGE_DEFAULT_OTLP[lang] == ("grpc", 4317)
        env_map = derive_language_otlp_env("http://otel-col:4318", lang)
        assert env_map["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://otel-col:4317"
        assert env_map["OTEL_EXPORTER_OTLP_PROTOCOL"] == "grpc"


def test_pinned_images_and_annotations_present():
    registry_path = (
        Path(__file__).resolve().parents[2]
        / "opentelemetry_mcp_server"
        / "static"
        / "otel_lang_registry.json"
    )
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for lang in ("java", "python", "nodejs", "dotnet", "go"):
        img = registry["languages"][lang].get("auto_instrumentation_image", "")
        assert img and ":" in img and not img.endswith(":latest")

    assert CONTAINER_NAMES_ANNOTATION == "instrumentation.opentelemetry.io/container-names"
    assert DOTNET_RUNTIME_ANNOTATION == "instrumentation.opentelemetry.io/otel-dotnet-auto-runtime"
    assert GO_TARGET_EXE_ANNOTATION == "instrumentation.opentelemetry.io/otel-go-auto-target-exe"
