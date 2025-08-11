from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


class User(AbstractUser, BaseModel):
    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('AUTHOR', 'Author'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='AUTHOR')
    bio = models.TextField(blank=True, null=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    # USERNAME_FIELD = 'email'
    # REQUIRED_FIELDS = ['username']

    def __str__(self):
        return f"{self.username} ({self.role})"

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
