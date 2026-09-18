"""
Consistent error envelope for the whole API (PRD API conventions):

    {"error": {"code": "...", "message": "...", "details": {...}}}

Error codes are stable strings that clients may branch on, so they are
part of the API contract and must not be renamed casually.
"""
import logging

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class APIError(exceptions.APIException):
    """Base for domain errors that carry a machine-readable code."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "error"
    default_detail = "A problem occurred."

    def __init__(self, message=None, code=None, details=None, status_code=None):
        self.message = message or self.default_detail
        self.code = code or self.default_code
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message, self.code)


class InvalidTransition(APIError):
    """An order status change that the state machine disallows."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "INVALID_TRANSITION"
    default_detail = "That status change is not allowed."


class InsufficientStock(APIError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "INSUFFICIENT_STOCK"
    default_detail = "Not enough stock available."


class StoreAccessDenied(APIError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "STORE_ACCESS_DENIED"
    default_detail = "You do not have access to this store."


# Map DRF's built-in exceptions onto stable codes.
_DRF_CODES = {
    exceptions.NotAuthenticated: "NOT_AUTHENTICATED",
    exceptions.AuthenticationFailed: "AUTHENTICATION_FAILED",
    exceptions.PermissionDenied: "PERMISSION_DENIED",
    exceptions.NotFound: "NOT_FOUND",
    exceptions.MethodNotAllowed: "METHOD_NOT_ALLOWED",
    exceptions.Throttled: "THROTTLED",
    exceptions.ParseError: "PARSE_ERROR",
    exceptions.UnsupportedMediaType: "UNSUPPORTED_MEDIA_TYPE",
    exceptions.ValidationError: "VALIDATION_ERROR",
}


def _code_for(exc):
    for klass, code in _DRF_CODES.items():
        if isinstance(exc, klass):
            return code
    return "ERROR"


def api_exception_handler(exc, context):
    """DRF EXCEPTION_HANDLER: wrap every error in the standard envelope."""
    # Normalise Django exceptions into DRF ones first.
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    if isinstance(exc, APIError):
        return Response(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
            status=exc.status_code,
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        # Unhandled: log it and return an opaque 500 rather than a traceback.
        view = context.get("view")
        logger.exception("Unhandled exception in %s", view.__class__.__name__
                         if view else "unknown view")
        return Response(
            {
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                    "details": {},
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    detail = response.data
    code = _code_for(exc)

    if isinstance(exc, exceptions.ValidationError):
        # Field errors go in details; the message stays human-readable.
        message = "The submitted data is invalid."
        details = detail if isinstance(detail, dict) else {"errors": detail}
    else:
        if isinstance(detail, dict) and "detail" in detail:
            message = str(detail["detail"])
            details = {}
        elif isinstance(detail, list):
            message = str(detail[0]) if detail else "Request failed."
            details = {"errors": detail}
        else:
            message = str(detail)
            details = {}

    response.data = {
        "error": {"code": code, "message": message, "details": details}
    }
    return response
