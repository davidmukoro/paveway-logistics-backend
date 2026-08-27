# utils.py
from urllib import request

from django.utils import timezone
from .models import Codesec
from .models import Auditlog


def generate_staffNo(staffCode, code):
    current_year = timezone.now().year

    try:
        num = Codesec.objects.get(code=code)
    except Codesec.DoesNotExist:
        num = Codesec.objects.create(code=code, counter=1)
    else:
        num.counter += 1
        num.save()

    lastNo = num.counter
    fstaffNo = staffCode + str(lastNo).rjust(3, "0")  # KSC005
    num.lastRecord = fstaffNo
    num.save()

    return fstaffNo


def generate_transid(code):
    current_year = timezone.now().year

    try:
        num = Codesec.objects.get(code=code, year=current_year)
    except Codesec.DoesNotExist:
        num = Codesec.objects.create(code=code, counter=1, year=current_year)
    else:
        num.counter += 1
        num.save()

    lastNo = num.counter
    transid = (
        code + str("-") + str(current_year) + str("-") + str(lastNo).rjust(3, "0")
    )  # BK-2024-001
    num.lastRecord = transid
    num.save()

    return transid


def generate_seriality(code):
    current_year = timezone.now().year

    try:
        num = Codesec.objects.get(code=code)
    except Codesec.DoesNotExist:
        num = Codesec.objects.create(code=code, counter=1, year=current_year)
    else:
        num.counter += 1
        num.save()

    lastNo = num.counter
    transid = code + str(lastNo).rjust(2, "0")  # BK-2024-001
    num.lastRecord = transid
    num.save()

    return transid


def log_user_activity(request, activity_description):
    user = request.user if request.user.is_authenticated else None
    ip = get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")

    # Create an audit log entry
    Auditlog.objects.create(
        user=user, activity=activity_description, ip=ip, user_agent=user_agent
    )


def get_client_ip(request):
    """Utility to extract IP address from request"""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def getCloudinaryPath(file):
    cloud_name = "dc5id3nl2"  # Set Cloudinary cloud name
    return f"https://res.cloudinary.com/{cloud_name}/image/upload/{file}"


from .models import Auditlog


def log_activity(request, user, activity):
    ip = None
    if request:
        ip = request.META.get("REMOTE_ADDR")

    user_agent = ""
    if request:
        user_agent = request.META.get("HTTP_USER_AGENT", "")

    Auditlog.objects.create(user=user, activity=activity, ip=ip, user_agent=user_agent)


# def get_client_ip(request):
#     x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
#     if x_forwarded_for:
#         return x_forwarded_for.split(",")[0]
#     return request.META.get("REMOTE_ADDR")

from rest_framework import viewsets
from decimal import Decimal
import uuid
from django.db.models.fields.files import FieldFile

# If you use this elsewhere, make sure it's imported
# from .models import Auditlog
# from .utils import get_client_ip


class AuditedModelViewSet(viewsets.ModelViewSet):
    """
    Base ViewSet that automatically logs user activity
    for create, update, delete, and retrieve actions.
    """

    def get_model_label(self):
        return self.queryset.model.__name__

    def safe_json(self, value):

        if isinstance(value, uuid.UUID):
            return str(value)

        if isinstance(value, Decimal):
            return float(value)

        if isinstance(value, FieldFile):
            try:
                return value.url
            except Exception:
                return str(value.name)

        if hasattr(value, "isoformat"):
            return value.isoformat()

        if isinstance(value, dict):
            return {k: self.safe_json(v) for k, v in value.items()}

        if isinstance(value, list):
            return [self.safe_json(v) for v in value]

        return value

    # def serialize_instance(self, instance):
    #     data = {}

    #     for field in instance._meta.fields:
    #         value = getattr(instance, field.name)

    #         # 🔥 ForeignKey handling (safe)
    #         if field.is_relation:
    #             if value is None:
    #                 data[field.name] = None
    #             else:
    #                 data[field.name] = {
    #                     "id": str(getattr(value, "id", None)),
    #                     "label": str(value),
    #                 }

    #         # 🔥 IMPORTANT: run safe_json for ALL remaining cases
    #         else:
    #             data[field.name] = self.safe_json(value)

    #     return data
    def serialize_instance(self, instance):
        data = {}

        for field in instance._meta.fields:

            # ForeignKey
            if field.is_relation:
                related_id = getattr(instance, field.attname)

                if related_id is None:
                    data[field.name] = None
                else:
                    related_object = getattr(instance, field.name, None)

                    data[field.name] = {
                        "id": str(related_id),
                        "label": str(related_object) if related_object else None,
                    }

            else:
                value = getattr(instance, field.name)
                data[field.name] = self.safe_json(value)

        return data

    def get_changes(self, old, new):
        changes = {}
        for key in new:
            if old.get(key) != new.get(key):
                changes[key] = {"from": old.get(key), "to": new.get(key)}
        return changes

    # def create(self, request, *args, **kwargs):
    #     response = super().create(request, *args, **kwargs)

    #     Auditlog.objects.create(
    #         user=request.user,
    #         action="CREATE",
    #         model=self.get_model_label(),
    #         object_id=str(response.data.get("id")),
    #         after=self.safe_json(response.data),
    #         ip_address=get_client_ip(request),
    #     )

    #     return response
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)

        object_id = response.data.get("id")

        instance = self.queryset.model.objects.get(pk=object_id)

        Auditlog.objects.create(
            user=request.user,
            action="CREATE",
            model=self.get_model_label(),
            object_id=str(instance.pk),
            after=self.serialize_instance(instance),
            ip_address=get_client_ip(request),
        )

        return response

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        old_data = self.serialize_instance(instance)

        response = super().update(request, *args, **kwargs)

        new_instance = self.get_object()
        new_data = self.serialize_instance(new_instance)

        Auditlog.objects.create(
            user=request.user,
            action="UPDATE",
            model=self.get_model_label(),
            object_id=str(new_instance.id),
            before=old_data,
            after=new_data,
            changes=self.get_changes(old_data, new_data),
            ip_address=get_client_ip(request),
        )

        return response

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()

        old_data = self.serialize_instance(instance)

        response = super().partial_update(request, *args, **kwargs)

        new_instance = self.get_object()
        new_data = self.serialize_instance(new_instance)

        Auditlog.objects.create(
            user=request.user,
            action="UPDATE",
            model=self.get_model_label(),
            object_id=str(new_instance.id),
            before=old_data,
            after=new_data,
            changes=self.get_changes(old_data, new_data),
            ip_address=get_client_ip(request),
        )

        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        old_data = self.serialize_instance(instance)
        object_id = str(instance.id)

        response = super().destroy(request, *args, **kwargs)

        Auditlog.objects.create(
            user=request.user,
            action="DELETE",
            model=self.get_model_label(),
            object_id=object_id,
            before=old_data,
            ip_address=get_client_ip(request),
        )

        return response

    def log_action(
        self,
        request,
        action,
        instance,
        before=None,
        after=None,
        changes=None,
    ):
        Auditlog.objects.create(
            user=request.user,
            action=action,
            model=instance.__class__.__name__,
            object_id=str(instance.pk),
            before=self.safe_json(before),
            after=self.safe_json(after),
            changes=self.safe_json(changes),
            ip_address=get_client_ip(request),
        )
