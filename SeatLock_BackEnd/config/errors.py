class AppError(Exception):
    status = 500

    def __init__(self, message="", **extra):
        super().__init__(message)
        self.message = message
        self.extra = extra


class ValidationFailed(AppError):
    status = 400


class AuthRequired(AppError):
    status = 401


class Forbidden(AppError):
    status = 403


class NotFound(AppError):
    status = 404


class Conflict(AppError):       # seat or version conflict -> 409
    status = 409


class HoldExpired(Conflict):
    pass


class LockTimeout(AppError):    # lock wait > 2s -> 503
    status = 503