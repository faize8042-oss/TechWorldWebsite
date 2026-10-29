"""Linux-only production transport; never load this in native Windows Gunicorn."""
import os
import socket
import stat

bind = "unix:/run/codeventra/gunicorn.sock"
workers = 2
umask = 0o117  # socket 0660; directory is separately provisioned 2750
worker_tmp_dir = "/tmp"
accesslog = "-"
errorlog = "-"
secure_scheme_headers = {}  # Django alone consumes Nginx's overwritten scheme.
forwarded_allow_ips = ""


def post_worker_init(worker):
    from django.conf import settings
    from django.core.checks import run_checks

    if settings.DEPLOYMENT_MODE != "production" or settings.PRODUCTION_PROXY_TRANSPORT != "unix":
        raise RuntimeError("Production socket settings required")
    if run_checks():
        raise RuntimeError("Production configuration checks failed")
    directory = os.stat("/run/codeventra")
    if (directory.st_uid, directory.st_gid, stat.S_IMODE(directory.st_mode)) != (10001, 10002, 0o2750):
        raise RuntimeError("Unsafe socket directory ownership or permissions")
    if not worker.sockets or any(
        listener.family != socket.AF_UNIX
        or listener.getsockname() != "/run/codeventra/gunicorn.sock"
        for listener in worker.sockets
    ):
        raise RuntimeError("Only the private Unix listener is permitted")
    node = os.stat("/run/codeventra/gunicorn.sock")
    if not stat.S_ISSOCK(node.st_mode) or (node.st_uid, node.st_gid, stat.S_IMODE(node.st_mode)) != (10001, 10002, 0o660):
        raise RuntimeError("Unsafe socket ownership or permissions")
    if worker.cfg.secure_scheme_headers:
        raise RuntimeError("Gunicorn scheme headers must be disabled")
    application = worker.wsgi

    def private_socket_application(environ, start_response):
        # This non-HTTP WSGI key cannot be populated by a client header.
        environ["codeventra.private_socket"] = True
        return application(environ, start_response)

    worker.wsgi = private_socket_application
