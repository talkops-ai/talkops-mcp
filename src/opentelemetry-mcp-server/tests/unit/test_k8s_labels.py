"""Test Kubernetes label utilities."""

from opentelemetry_mcp_server.utils.k8s_labels import (
    build_label_selector,
    build_otel_operator_selector,
    detect_language_from_annotations,
    detect_language_from_image,
    detect_language_from_images,
    detect_language_from_name,
    detect_language_from_runtime_env,
    detect_signals_from_env,
    get_instrumentation_cr_from_annotations,
    has_otel_sdk_env,
)


class TestK8sLabels:
    """Test Kubernetes label utilities."""

    def test_build_operator_selector(self) -> None:
        selector = build_otel_operator_selector()
        assert "app.kubernetes.io/managed-by=opentelemetry-operator" in selector

    def test_build_label_selector(self) -> None:
        selector = build_label_selector({"app": "test", "env": "prod"})
        assert "app=test" in selector
        assert "env=prod" in selector

    def test_detect_language_true(self) -> None:
        annotations = {
            "instrumentation.opentelemetry.io/inject-java": "true",
        }
        assert detect_language_from_annotations(annotations) == "java"

    def test_detect_language_cr_name(self) -> None:
        annotations = {
            "instrumentation.opentelemetry.io/inject-python": "my-instrumentation",
        }
        assert detect_language_from_annotations(annotations) == "python"

    def test_detect_language_none(self) -> None:
        annotations = {"unrelated": "value"}
        assert detect_language_from_annotations(annotations) is None

    def test_detect_language_false(self) -> None:
        annotations = {
            "instrumentation.opentelemetry.io/inject-java": "false",
        }
        assert detect_language_from_annotations(annotations) is None

    def test_get_cr_name_from_annotation(self) -> None:
        annotations = {
            "instrumentation.opentelemetry.io/inject-python": "custom-instr",
        }
        assert get_instrumentation_cr_from_annotations(annotations) == "custom-instr"

    def test_get_cr_name_true_returns_none(self) -> None:
        annotations = {
            "instrumentation.opentelemetry.io/inject-java": "true",
        }
        assert get_instrumentation_cr_from_annotations(annotations) is None


class TestLanguageDetectionFromImage:
    """Test image-based language detection."""

    def test_java_suffix(self) -> None:
        assert detect_language_from_image("otel-demo-java:latest") == "java"

    def test_python_suffix(self) -> None:
        assert detect_language_from_image("recommendation-python:1.0") == "python"

    def test_nodejs_suffix(self) -> None:
        assert detect_language_from_image("frontend-nodejs:v2") == "nodejs"

    def test_node_suffix(self) -> None:
        assert detect_language_from_image("my-app-node:latest") == "nodejs"

    def test_dotnet_suffix(self) -> None:
        assert detect_language_from_image("my-app-dotnet:7.0") == "dotnet"

    def test_go_suffix(self) -> None:
        assert detect_language_from_image("my-app-go:latest") == "go"

    def test_golang_suffix(self) -> None:
        assert detect_language_from_image("my-app-golang:latest") == "go"

    def test_rust_suffix(self) -> None:
        assert detect_language_from_image("my-app-rust:latest") == "rust"

    def test_openjdk_base(self) -> None:
        assert detect_language_from_image("openjdk:17") == "java"

    def test_python_base(self) -> None:
        assert detect_language_from_image("python:3.11") == "python"

    def test_node_base(self) -> None:
        assert detect_language_from_image("node:20") == "nodejs"

    def test_no_match(self) -> None:
        assert detect_language_from_image("alpine:3.18") is None

    def test_empty_string(self) -> None:
        assert detect_language_from_image("") is None

    def test_registry_prefix(self) -> None:
        assert detect_language_from_image("gcr.io/my-project/my-app-python:latest") == "python"


class TestLanguageDetectionFromImages:
    """Test multi-image language detection."""

    def test_first_match_wins(self) -> None:
        images = ["alpine:3.18", "otel-demo-python:latest"]
        assert detect_language_from_images(images) == "python"

    def test_no_match(self) -> None:
        images = ["alpine:3.18", "nginx:latest"]
        assert detect_language_from_images(images) is None


class TestDetectSignalsFromEnv:
    """Test OTel signal detection from environment variables."""

    def test_traces_detected(self) -> None:
        env = {"OTEL_TRACES_EXPORTER": "otlp"}
        assert detect_signals_from_env(env) == ["traces"]

    def test_metrics_detected(self) -> None:
        env = {"OTEL_METRICS_EXPORTER": "otlp"}
        assert detect_signals_from_env(env) == ["metrics"]

    def test_logs_detected(self) -> None:
        env = {"OTEL_LOGS_EXPORTER": "otlp"}
        assert detect_signals_from_env(env) == ["logs"]

    def test_all_signals(self) -> None:
        env = {
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_METRICS_EXPORTER": "otlp",
            "OTEL_LOGS_EXPORTER": "otlp",
        }
        assert set(detect_signals_from_env(env)) == {"traces", "metrics", "logs"}

    def test_none_exporter_excluded(self) -> None:
        env = {
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_METRICS_EXPORTER": "none",
        }
        assert detect_signals_from_env(env) == ["traces"]

    def test_empty_env(self) -> None:
        assert detect_signals_from_env({}) == []

    def test_from_ref_sentinel_treated_as_enabled(self) -> None:
        """Env vars from configMap/secret refs should still detect signals."""
        env = {"OTEL_TRACES_EXPORTER": "<from-ref>"}
        assert detect_signals_from_env(env) == ["traces"]


class TestLanguageDetectionFromTagSuffix:
    """Test OTel Demo-style tag-suffix patterns."""

    def test_otel_demo_java(self) -> None:
        assert detect_language_from_image("ghcr.io/open-telemetry/demo:latest-java") == "java"

    def test_otel_demo_python(self) -> None:
        assert detect_language_from_image("ghcr.io/open-telemetry/demo:1.12.0-python") == "python"

    def test_otel_demo_nodejs(self) -> None:
        assert detect_language_from_image("ghcr.io/open-telemetry/demo:latest-nodejs") == "nodejs"

    def test_otel_demo_dotnet(self) -> None:
        assert detect_language_from_image("ghcr.io/open-telemetry/demo:latest-dotnet") == "dotnet"

    def test_otel_demo_go(self) -> None:
        assert detect_language_from_image("ghcr.io/open-telemetry/demo:latest-go") == "go"

    def test_no_tag_suffix_match(self) -> None:
        assert detect_language_from_image("ghcr.io/open-telemetry/demo:latest-adservice") is None


class TestLanguageDetectionFromName:
    """Test deployment/container name-based language heuristics."""

    def test_spring_app(self) -> None:
        assert detect_language_from_name("my-spring-service") == "java"

    def test_flask_api(self) -> None:
        assert detect_language_from_name("flask-api") == "python"

    def test_express_server(self) -> None:
        assert detect_language_from_name("express-backend") == "nodejs"

    def test_aspnet_service(self) -> None:
        assert detect_language_from_name("aspnet-gateway") == "dotnet"

    def test_gin_service(self) -> None:
        assert detect_language_from_name("gin-auth-service") == "go"

    def test_rails_app(self) -> None:
        assert detect_language_from_name("rails-webapp") == "ruby"

    def test_laravel_app(self) -> None:
        assert detect_language_from_name("laravel-api") == "php"

    def test_no_match_generic_name(self) -> None:
        """Generic names like 'adservice' should not match."""
        assert detect_language_from_name("adservice") is None

    def test_no_match_empty(self) -> None:
        assert detect_language_from_name("") is None


class TestHasOtelSdkEnv:
    """Test has_otel_sdk_env utility."""

    def test_has_otel_vars(self) -> None:
        env = {"OTEL_SERVICE_NAME": "my-svc", "APP_PORT": "8080"}
        assert has_otel_sdk_env(env) is True

    def test_no_otel_vars(self) -> None:
        env = {"APP_PORT": "8080", "DB_HOST": "localhost"}
        assert has_otel_sdk_env(env) is False

    def test_empty_env(self) -> None:
        assert has_otel_sdk_env({}) is False

    def test_from_ref_sentinel(self) -> None:
        env = {"OTEL_EXPORTER_OTLP_ENDPOINT": "<from-ref>"}
        assert has_otel_sdk_env(env) is True


class TestDetectLanguageFromRuntimeEnv:
    """Test runtime env var-based language detection."""

    def test_java_home(self) -> None:
        env = {"JAVA_HOME": "/usr/lib/jvm/java-17", "PATH": "/usr/bin"}
        assert detect_language_from_runtime_env(env) == "java"

    def test_java_tool_options(self) -> None:
        env = {"JAVA_TOOL_OPTIONS": "-javaagent:/otel/agent.jar"}
        assert detect_language_from_runtime_env(env) == "java"

    def test_pythonpath(self) -> None:
        env = {"PYTHONPATH": "/app", "OTEL_SERVICE_NAME": "my-svc"}
        assert detect_language_from_runtime_env(env) == "python"

    def test_pythonunbuffered(self) -> None:
        env = {"PYTHONUNBUFFERED": "1"}
        assert detect_language_from_runtime_env(env) == "python"

    def test_dotnet_running_in_container(self) -> None:
        env = {"DOTNET_RUNNING_IN_CONTAINER": "true"}
        assert detect_language_from_runtime_env(env) == "dotnet"

    def test_aspnetcore_urls(self) -> None:
        env = {"ASPNETCORE_URLS": "http://+:8080"}
        assert detect_language_from_runtime_env(env) == "dotnet"

    def test_node_version(self) -> None:
        env = {"NODE_VERSION": "20.11.0"}
        assert detect_language_from_runtime_env(env) == "nodejs"

    def test_gopath(self) -> None:
        env = {"GOPATH": "/go"}
        assert detect_language_from_runtime_env(env) == "go"

    def test_ruby_version(self) -> None:
        env = {"RUBY_VERSION": "3.2.0", "GEM_HOME": "/usr/local/bundle"}
        assert detect_language_from_runtime_env(env) == "ruby"

    def test_rustup_home(self) -> None:
        env = {"RUSTUP_HOME": "/usr/local/rustup"}
        assert detect_language_from_runtime_env(env) == "rust"

    def test_php_ini_dir(self) -> None:
        env = {"PHP_INI_DIR": "/usr/local/etc/php"}
        assert detect_language_from_runtime_env(env) == "php"

    def test_no_runtime_env(self) -> None:
        env = {"APP_PORT": "8080", "DB_HOST": "localhost"}
        assert detect_language_from_runtime_env(env) is None

    def test_empty_env(self) -> None:
        assert detect_language_from_runtime_env({}) is None

    def test_otel_demo_scenario(self) -> None:
        """OTel Demo services have JAVA_TOOL_OPTIONS for auto-instrumentation."""
        env = {
            "JAVA_TOOL_OPTIONS": "-javaagent:/opentelemetry-javaagent.jar",
            "OTEL_SERVICE_NAME": "adservice",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel-collector:4317",
        }
        assert detect_language_from_runtime_env(env) == "java"

    def test_from_ref_sentinel_still_detects(self) -> None:
        """Env vars from valueFrom should still trigger detection."""
        env = {"JAVA_HOME": "<from-ref>"}
        assert detect_language_from_runtime_env(env) == "java"

