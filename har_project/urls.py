from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import FileResponse, Http404
import os


def serve_media_file(request, path):
    """Serve media files — works in both DEBUG and production.
    
    On shared hosting where Apache/Nginx is not configured to serve
    /media/, this view handles file delivery.
    """
    file_path = os.path.join(settings.MEDIA_ROOT, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(open(file_path, 'rb'))
    raise Http404("Media file not found")


urlpatterns = [
    path('', include('users.urls')),
]

# In DEBUG mode, Django's static() helper serves media
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # In production (shared hosting), add explicit media serving URL
    urlpatterns += [
        path('media/<path:path>', serve_media_file, name='serve_media'),
    ]
