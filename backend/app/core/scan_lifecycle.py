from datetime import datetime, timedelta, timezone


def expire_overdue_scans(db, model, statuses):
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=3700)
    changed = db.query(model).filter(model.status == statuses.RUNNING, model.started_at < cutoff).update({
        model.status: statuses.FAILED, model.stage: 'failed',
        model.error_message: 'Превышен общий лимит выполнения (1 час). Возможно, worker был остановлен. Запустите новый скан.',
        model.finished_at: datetime.now(timezone.utc),
    }, synchronize_session=False)
    if changed:
        db.commit()
        db.expire_all()
