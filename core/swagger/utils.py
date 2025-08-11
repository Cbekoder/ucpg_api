from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

from core.swagger.generator import BothHttpAndHttpsSchemaGenerator

main_schema_view = get_schema_view(
    openapi.Info(
        title="Universal Crypto Payment Gateway (UCPG) API",
        default_version="v1",
        description="API for anonymous cryptocurrency payment gateway that allows users to make payments in local currency and receive funds via one-time QR codes and links. Supports multi-currency transactions, provider integrations, and commission management.",
        contact=openapi.Contact(email="support@ucpg.com"),
        terms_of_service="https://ucpg.com/terms/",
        license=openapi.License(name="Proprietary License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
    generator_class=BothHttpAndHttpsSchemaGenerator,
)
