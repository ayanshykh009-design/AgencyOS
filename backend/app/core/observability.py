"""OpenTelemetry instrumentation (optional, off by default).

Enabled with OTEL_ENABLED=true; traces are exported via OTLP/HTTP to
OTEL_ENDPOINT. All imports are lazy so the app still starts if the
instrumentation packages are not installed.
"""
import logging

from fastapi import FastAPI

from app.core.config import settings

logger = logging.getLogger("agencyos")


def setup_telemetry(app: FastAPI) -> None:
    """Configure the tracer provider and instrument FastAPI (no-op by default)."""
    if not settings.OTEL_ENABLED:
        logger.debug("OpenTelemetry disabled")
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(
            resource=Resource.create({"service.name": settings.OTEL_SERVICE_NAME})
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.OTEL_ENDPOINT))
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        logger.info("OpenTelemetry enabled (endpoint=%s)", settings.OTEL_ENDPOINT)
    except ImportError:
        logger.warning("OpenTelemetry packages not installed; telemetry disabled")
