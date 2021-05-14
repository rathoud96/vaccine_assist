from apscheduler.schedulers.background import BackgroundScheduler


def scheduler(job):
    scheduler = BackgroundScheduler()
    scheduler.add_job(job, "interval", seconds=60)
    scheduler.start()
