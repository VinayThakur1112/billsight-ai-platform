resource "google_pubsub_topic" "bill_upload" {
  name = "bill-upload-events"
}

resource "google_pubsub_topic" "dead_letter" {
  name = "bill-dead-letter-events"
}

resource "google_pubsub_subscription" "ingestion_sub" {
  name  = "bill-ingestion-sub"
  topic = google_pubsub_topic.bill_upload.name

  ack_deadline_seconds = 30

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }
}