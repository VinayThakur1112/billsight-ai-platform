import os
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    PeriodicExportingMetricReader
)
from opentelemetry.exporter.cloud_monitoring import (
    CloudMonitoringMetricsExporter
)
from opentelemetry.sdk.resources import Resource

PROJECT_ID = os.getenv("PROJECT_ID")

# ------------------------------------------------------
# Resource = metadata attached to ALL metrics
# ------------------------------------------------------
resource = Resource.create({
    "service.name": "ocr-worker",
    "service.version": "1.0.0",
    "service.namespace": "document-processing"
})

# ------------------------------------------------------
# Exporter → Google Cloud Monitoring
# ------------------------------------------------------
exporter = CloudMonitoringMetricsExporter(
    project_id=PROJECT_ID
)

reader = PeriodicExportingMetricReader(
    exporter,
    export_interval_millis=60_000  # export every 60s
)

# ------------------------------------------------------
# Meter Provider (GLOBAL)
# ------------------------------------------------------
provider = MeterProvider(
    resource=resource,
    metric_readers=[reader]
)

metrics.set_meter_provider(provider)

# ------------------------------------------------------
# Meter
# ------------------------------------------------------
meter = metrics.get_meter("ocr.metrics")

# ------------------------------------------------------
# Metric instruments
# ------------------------------------------------------
processing_latency = meter.create_histogram(
    name="ocr_processing_latency_seconds",
    unit="s",
    description="End-to-end OCR processing latency"
)

message_counter = meter.create_counter(
    name="ocr_messages_processed_total",
    description="Total OCR messages processed"
)

failure_counter = meter.create_counter(
    name="ocr_processing_failures_total",
    description="Total OCR processing failures"
)