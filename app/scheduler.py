from apscheduler.schedulers.background import BackgroundScheduler


def scheduler(job):
    scheduler = BackgroundScheduler()
    scheduler.add_job(job, "interval", seconds=60, misfire_grace_time=300)
    scheduler.start()
