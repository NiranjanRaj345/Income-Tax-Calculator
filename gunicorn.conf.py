import multiprocessing

# Worker configuration
workers = multiprocessing.cpu_count() * 2 + 1
threads = 2
worker_class = 'sync'

# Binding
bind = "0.0.0.0:10000"

# Timeout configuration
timeout = 120
keepalive = 5

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'
