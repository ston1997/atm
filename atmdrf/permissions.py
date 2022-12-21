from rest_framework import permissions


class IsOwnerAccount(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return obj == request.user

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsAnonymous(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(not request.user.is_authenticated)
