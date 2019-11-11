
import multiprocessing

MAX_WORKERS = 4

workers = min(multiprocessing.cpu_count() + 1, MAX_WORKERS)

max_requests = 1000
