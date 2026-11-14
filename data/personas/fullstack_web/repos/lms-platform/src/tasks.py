from celery import Celery

app = Celery("lms-platform", broker="redis://redis:6379/0")


@app.task(bind=True, max_retries=3, default_retry_delay=30)
def process_item(self, item_id: str) -> dict:
    try:
        return run_pipeline(item_id)
    except TransientError as exc:
        raise self.retry(exc=exc)
