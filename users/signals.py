from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import User


@receiver(post_save, sender=User)
def invalidate_face_cache_on_save(sender, instance, created, **kwargs):
    """Invalidate the in-memory face encoding cache whenever an employee is saved."""
    if instance.role != 'employee' or instance.is_superuser or instance.is_staff:
        return
    try:
        from . import face_rec
        face_rec.invalidate_cache()
    except Exception:
        pass


@receiver(post_delete, sender=User)
def invalidate_on_delete(sender, instance, **kwargs):
    try:
        from . import face_rec
        face_rec.invalidate_cache()
    except Exception:
        pass
