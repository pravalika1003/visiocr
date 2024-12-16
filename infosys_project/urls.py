from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', lambda request: redirect('landing_page')),  # Redirect root URL to login page
    path('register/', include('ocrapp.urls')),
    path('login/', include('ocrapp.urls')),
    path('logout/', include('ocrapp.urls')),
    path('upload/', include('ocrapp.urls')),
    path('user-admin/', include('ocrapp.urls')),
    path('landing_page/', include('ocrapp.urls')),

    path('admin/', admin.site.urls),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
