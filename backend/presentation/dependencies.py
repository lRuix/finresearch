"""Dependency injection from the service container."""
from __future__ import annotations

from presentation.api import routes


def get_repository():
    return routes.container.repository


def get_datasource():
    return routes.container.datasource


def get_sync_service():
    return routes.container.sync_service


def get_analysis_service():
    return routes.container.analysis_service


def get_screening_service():
    return routes.container.screening_service


def get_recommendation_service():
    return routes.container.recommendation_service


def get_comparison_service():
    return routes.container.comparison_service
