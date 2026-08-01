"""Endpoint package: HTTP route handlers.

Rule: handlers must be thin. Delegate to app/services/ for business logic and
app/repositories/ for data access. This package only maps HTTP <=> service calls.
"""
