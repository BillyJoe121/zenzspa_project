from types import SimpleNamespace

from core.permissions import IsAuthenticatedAndActive, ReadOnly, IsAdmin, IsStaff, RoleAllowed


def test_is_authenticated_and_active_permission():
    perm = IsAuthenticatedAndActive()
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, is_active=True))
    assert perm.has_permission(request, None) is True

    request.user.is_active = False
    assert perm.has_permission(request, None) is False

    request.user.is_authenticated = False
    assert perm.has_permission(request, None) is False


def test_read_only_allows_only_safe_methods():
    perm = ReadOnly()
    assert perm.has_permission(SimpleNamespace(method="GET"), None) is True
    assert perm.has_permission(SimpleNamespace(method="POST"), None) is False


def test_is_admin_and_is_staff_permissions():
    admin_perm = IsAdmin()
    staff_perm = IsStaff()

    admin_user = SimpleNamespace(role="ADMIN", is_authenticated=True)
    staff_user = SimpleNamespace(role="STAFF", is_authenticated=True)
    client_user = SimpleNamespace(role="CLIENT", is_authenticated=True)
    anon_user = SimpleNamespace(role="ADMIN", is_authenticated=False)

    assert admin_perm.has_permission(SimpleNamespace(user=admin_user), None) is True
    assert admin_perm.has_permission(SimpleNamespace(user=client_user), None) is False
    assert admin_perm.has_permission(SimpleNamespace(user=anon_user), None) is False

    assert staff_perm.has_permission(SimpleNamespace(user=staff_user), None) is True
    assert staff_perm.has_permission(SimpleNamespace(user=admin_user), None) is True
    assert staff_perm.has_permission(SimpleNamespace(user=client_user), None) is False
    assert staff_perm.has_permission(SimpleNamespace(user=anon_user), None) is False


def test_role_allowed_validates_required_roles_types_and_members(caplog):
    perm = RoleAllowed()
    caplog.set_level("ERROR")

    unauth_request = SimpleNamespace(user=None)
    assert perm.has_permission(unauth_request, SimpleNamespace(required_roles={"ADMIN"})) is False

    # required_roles no definido -> permitido
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, role="CLIENT"))
    assert perm.has_permission(request, SimpleNamespace(required_roles=None)) is True

    # required_roles tipo inválido
    assert perm.has_permission(request, SimpleNamespace(required_roles="ADMIN")) is False
    assert any("required_roles debe ser un set/list/tuple" in rec.message for rec in caplog.records)

    # roles inválidos en el set
    caplog.clear()
    assert perm.has_permission(request, SimpleNamespace(required_roles={"GODMODE"})) is False
    assert any("Roles inválidos" in rec.message for rec in caplog.records)

    # rol de usuario no autorizado
    assert perm.has_permission(request, SimpleNamespace(required_roles={"ADMIN"})) is False

    # rol autorizado
    assert perm.has_permission(request, SimpleNamespace(required_roles={"CLIENT", "VIP"})) is True
