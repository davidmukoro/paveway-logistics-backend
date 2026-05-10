from rest_framework.permissions import BasePermission

class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        # Check if the user is authenticated and an admin
        return request.user and request.user.is_authenticated and request.user.role == 'Superadmin'

class IsMarketer(BasePermission):
     def has_permission(self, request, view):
        # Check if the user is authenticated and an admin
        return request.user and request.user.is_authenticated and request.user.role == 'Marketer'
class IsOperationStaff(BasePermission):
     def has_permission(self, request, view):
        # Check if the user is authenticated and an admin
        return request.user and request.user.is_authenticated and request.user.role == 'Account'
    
class IsCustomerSupport(BasePermission):
     def has_permission(self, request, view):
        # Check if the user is authenticated and an admin
        return request.user and request.user.is_authenticated and request.user.role == 'CustomerSupport'
    
class IsDelivery(BasePermission):
     def has_permission(self, request, view):
        # Check if the user is authenticated and an admin
        return request.user and request.user.is_authenticated and request.user.role == 'Delivery'
    
class IsAgent(BasePermission):
     def has_permission(self, request, view):
        # Check if the user is authenticated and an admin
        return request.user and request.user.is_authenticated and request.user.role == 'Agent'
class IsCustomer(BasePermission):
     def has_permission(self, request, view):
        # Check if the user is authenticated and an admin
        return request.user and request.user.is_authenticated and request.user.role == 'Customer'
    
class IsAuthenticatedAndStaff(BasePermission):
     def has_permission(self, request, view):
        # Check if the user is authenticated and an admin
        return request.user and request.user.is_authenticated and request.user.is_staff == True
    
class IsBackOffice(BasePermission):
     def has_permission(self, request, view):
        # Check if the user is authenticated and an admin
        return request.user and request.user.is_authenticated and request.user.is_staff == True

class IsSuperAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        # Allow superusers to perform all actions
        if request.user.is_superuser:
            return True
        # Allow authenticated users to perform read-only actions
        if request.method in ['GET']:
            return request.user.is_authenticated
        # Deny other actions for non-superusers
        return False
